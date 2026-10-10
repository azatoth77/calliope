# Voce, modello e regole sul testo

*Ciclo principale, modello della voce, tool calling, reti e spinte di Brain, regole deterministiche sul testo, azione in sospeso, robustezza. Documento d'area: nato il 06/10/2026 dividendo CLAUDE.md (proposta P7 di [`../ricerche/2026-10-06-analisi-complessiva.md`](../ricerche/2026-10-06-analisi-complessiva.md)). Chi lavora su quest'area aggiorna questo file; in CLAUDE.md al più una riga.*

**Stato al 09/10.** Sulla DGX la voce è gemma4 26B su Ollama (`llm_profilo`), 72 schemi di tool
uguali per ogni livello, con i nomi nuovi dei lavori e dello sviluppo dall'08/10 (i vecchi valgono
ancora nel registro, regola `tool_nome_vecchio`). Le reti di Brain e le regole sul testo seguono il
principio 10; le ultime entrate: «forse intendevi…» dopo un esito vuoto (08/10), il «no» che chiude
la proposta (09/10), la compagnia con il giudizio «rivolta a Calliope» in ombra (09/10). Molte
misure di questo documento sono col 4B in locale: da rifare col 26B sulla DGX dove è scritto.

## Moduli

| Stadio | Libreria | Dove |
|---|---|---|
| Ciclo principale | — | `calliope/main.py` → `main`, `Avvio` (i passi dell'avvio), `Corsie` (un ciclo per satellite), `single_instance_lock`, `check_audio_devices`, `notifica_systemd` (READY=1 per systemd); il ciclo della voce `calliope/ciclo.py` → `Ciclo` (`giro` in fasi, dal 06/10: P8), `Servizi`, `Turno`, `save_debug_audio`, `domanda_guardia` |
| Wake word testuale (ripiego, conferma, estrazione della richiesta), uscita, stop, cortesia | difflib sulla trascrizione | `calliope/wakeword.py` → `find_wake_word` (più parole, `start_only`), `exit_intent` / `exit_request`, `is_stop`, `closing_kind`, `said_name`, `nuova_conversazione_come` e `prefisso_nome` (storpiature, dal 10/10); `calliope/storpiature.py` → `suggerisci`, `nota` (forme chiuse storpiate da Whisper, dal 10/10); `calliope/cortesia.py` → `Cortesia` («Prego!», «Bene!» per tono); le parole in `Config.wake_names` (`wake_word`, dal 04/10) |
| LLM + tool calling | Ollama, API nativa `/api/chat` (httpx) o `/v1` (`openai`) | `calliope/brain.py` → `Brain`, `OllamaBackend`, `OpenAIBackend`; modello della voce in una riga, `llm_profilo` (`calliope/config.py` → `PROFILI_LLM`, con le reti adatte in `llm_reti_spente`); banco `prove/prova_regressione.py` |
| Tool nativi | — | `calliope/tools/` (`spec.py`, `registry.py`, `builtin.py`); argomenti che nominano qualcosa `ToolSpec.nomi` e la loro misura in Brain (`_argomenti_inizio`, `_argomenti_fine`, `argomenti_per_registro`, dal 08/10: [stt-tts](stt-tts.md)); forma degli argomenti ricondotta a quella del tool `ToolSpec.prepara` (dal 08/10) |
| Dati del turno (contesti prima della domanda, mai nel prompt di sistema) | — | `calliope/brain.py` → `TURN_CONTEXT_MSG`, `PENDING_MSG`, `AGENDA_MSG`, `SOSPESO_ALTRUI_MSG`, `EST_NOMINATA_MSG`, `RIFIUTO_MSG` (dal 09/10); modalità sviluppo `calliope/sviluppo.py` → `SVILUPPO_MSG`, `Sviluppi.dati_turno` (dal 08/10) |
| «La frase è rivolta a Calliope?» in compagnia (dal 09/10, in ombra) | Ollama, output strutturato sul modello del rilevatore di pericolo | `calliope/rivolta.py` → `Giudice`, `etichetta`; `Brain.dimentica_ultimo_turno`; la compagnia è in [stt-tts](stt-tts.md) |
| Pulizia output | regex | `calliope/brain.py` → `ThinkFilter`, `TextCallGuard`; `calliope/tts.py` → `split_sentences`, `clean_for_speech` |
| Configurazione | dataclass + YAML (PyYAML) | `calliope/config.py` → `Config`, `load_config`, `VOICE_MAP`; file `calliope.yaml` |
| Stato del dialogo (dal 10/10, in ombra) | — | `calliope/stato_dialogo.py` → `Proposta`, `StatoPersona`, `StatoCorsia`, `blocco`, `decidi`, `consenso_progetto`, `confronto`; corsia veloce `calliope/risposte.py` → `forma_chiusa`; tool di risposta `calliope/tools/proposta.py` → `proposta_rispondi`; in Brain `_dialogo_inizio`, `_proposta_rispondi`, `_dialogo_fine` (sezione «Stato del dialogo, passo 1») |
| Registro dei turni | JSONL, un file al giorno in `registro/` | `calliope/turnlog.py` → `TurnLog`; analisi con `revisione.py` |
| Registro degli eventi (dal 10/10, in ombra: passi 0 e 1 della decisione 0027) | SQLite in WAL, tabella `eventi` di `conversazioni.db` | `calliope/eventi/` → `tipi.py` (`TIPI`, `Evento`, `per_disco`), `registro.py` (`Registro`, `Registri`, `Disco`, `porta_annuncio`, `porta_avviso_tutore`, `porta_coda`, `porta_riassegna`, `stato_disco`), `proiezioni.py` (`PROIEZIONE_CONTESTO`, `PROIEZIONE_TURNI`, `turni`, `messaggi`, `contesto`), `misura.py` (`misura_finestra`, `motivi_parlato`, `riassunto`), `ombra.py` (`Ombra`), dal passo 2 (10/10) `uscita.py` (`Uscita`, `per_voce`: l'uscita unica verso la voce) e l'elenco degli atti `tipi.ATTI`; ciclo `Ciclo._scrivi_turno`, `Ciclo._conversazioni_dimenticate`; `Brain.dimentica_conversazione` (sezione «Una voce sola, passi 0 e 1») |
| Persistenza comune | SQLite in WAL, file di stato atomici, versioni dello schema | `calliope/persistenza.py` → `apri_db`, `scrivi_atomico` / `scrivi_json` / `leggi_json`, `migra` / `prepara_schema` (tabella `meta_schema`) |

## Problemi noti

*Fuse il 09/10 le due sezioni nate dalla divisione di CLAUDE.md (stato e problemi fino al 06/10): ogni voce una volta sola, le superate segnate come storiche.*

  - **Tool calling nativo**: 20 tool (ora, data, calcola, timer, promemoria, agenda,
    annulla, chi parla, voci, utenti, cambio voce, rinomina, registrazione, ricorda,
    dimentica, tre per le liste, due per gli appuntamenti), filtrati per livello di chi
    parla; 21 con la biblioteca; 8 in più con il PC, 2 con i documenti, 3 con la casa
    (34 in tutto; senza Home Assistant configurato resta solo `casa_integrazione`); dal
    01/10 `calliope_stato` e i 3 delle installazioni (38); dal 02/10 `schermo_mostra` e
    `schermo_gestisci` (40), e con un agente configurato `delega_lavoro`, `lavori_stato`,
    `lavori_annulla` (43). *[Conteggi storici: il 06/10 i tool sono 65 schemi, con 65 classi in `politica.CLASSI`.]* *[Superato l'08/10: 72 schemi sulla DGX (più `esercizi` con un minore), e i tool dei lavori si chiamano `lavoro_affida`, `lavoro_stato`, `lavoro_annulla`… (sezione «Modalità sviluppo, versione 2»).]*

  - **Registro dei turni** (`registro/`) per l'auto-miglioramento.

- **Robustezza** (03/10, analisi in `prove/prova_robustezza.py`, una sezione per difetto): i thread della voce non muoiono (frase saltata nel log, uscita guasta riaperta da sola, `Speaker.wait()` con tempo massimo e thread rifatti); il giro del ciclo principale è `giro()` dentro un try (scuse, errore nel registro dei turni, si continua; 5 errori in 120 s → uscita con errore per systemd); `TurnLog.write` non solleva; Whisper passa alla CPU anche durante l'uso, con una frase d'attesa; all'avvio si aspetta il modello (`llm_attesa_avvio_s`, 15 minuti) invece di uscire. `memoria.db` in WAL con `busy_timeout` 30 s per tutti i servizi (`apri_db`); il thread dell'agenda riprova dopo un errore; la numerazione prenota il numero, prepara i file **fuori** dalla transazione e lo conferma (se fallisce: libero se è l'ultimo, altrimenti annullato con la nota). `speakers.json` atomico con la copia `.bak`: un file illeggibile **non** è un primo avvio (tutti ospiti, nessun salvataggio sopra, capacità «chi_parla» guasta). Ogni database ha la sua versione in `meta_schema`: dati di una versione più nuova si aprono in sola lettura. Il gestore ferma il servizio prima di ripristinare, sposta -wal/-shm/-journal con il database e copia anche `archivio.db`. «Tra N minuti» è tempo reale (ora legale). Restano: le attese fisse di `prova_satellite` (negative o di assestamento) e la soglia di 50 ms in `prova_agenti` (fallita una volta sotto carico, 51,7 ms).

- **`localhost` su Windows**: Ollama ascolta solo su IPv4 e ogni nuova connessione a
  `localhost` perde ~2 s nel tentativo IPv6. Usare sempre `127.0.0.1` in `llm_base_url`.

- **L'LLM si inventa capacità** che non ha (es. "posso cambiare voce"): il prompt di
  sistema non dice cosa Calliope non sa fare. *[Superato dal 01/10: in fondo al prompt c'è
  l'elenco di cosa c'è e cosa manca (`capacita.testo_prompt`), vedi
  [capacita-installazioni](capacita-installazioni.md).]*

- **Modelli "ragionanti"**: misurato su `qwen3:8b`, con il thinking la prima frase passa
  da 0,57 s a 4,96 s di media (fino a 9,75 s) senza risposte visibilmente migliori.
  `Config.llm_reasoning_effort = "none"` lo spegne tramite l'API compatibile OpenAI
  (Ollama lo accetta anche sui modelli senza thinking; altri valori su quei modelli
  danno errore 400). Se un server non conosce il parametro, impostarlo a `None`.
  `strip_think` resta come rete di sicurezza per i blocchi `<think>` nel testo.

- **Tool con gemma4 e thinking spento**: a volte il modello scrive la chiamata come testo
  («chi_parla()», «chi_parla{}», «Chi_parla.» o il formato grezzo `call:cambia_voce{…}`),
  che finirebbe al TTS e, rimasta nella storia, verrebbe ripetuta nei turni dopo.
  `TextCallGuard` la intercetta e la esegue come chiamata vera. Con il thinking acceso i
  tool sono sempre giusti, ma la prima risposta passa da ~0,3 s a 0,6–2,5 s. Un prompt
  generico faceva dire «ora controllo l'ora» senza chiamare nulla: il prompt nomina i
  tool uno per uno. Dal 26/09 `TextCallGuard` riconosce anche i qualificatori («calliope.»,
  «default_api.», «call_») e le funzioni matematiche scritte come testo («sqrt(144)» diventa
  `calcola`); una risposta di una sola parola si trattiene per un token (~20 ms); le frasi che
  nominano un tool con «_» non si dicono (`Brain.mentions_tool`).

- **Wake word testuale**: soglia 0,78 e niente parole molto più corte del nome. Con 0,65
  «cavallo», «calcio», «calle» e «callo» svegliavano Calliope. Con il nome in mezzo e
  solo cortesia dopo («Apri il documento, Calliope, grazie.») vale la frase prima del nome
  (01/10: arrivava solo «grazie»); «Calliope, grazie» da solo resta «grazie».

- **Regole sul testo ristrette** (01/10, rapporto
  [`docs/ricerche/2026-10-01-regole-deterministiche.md`](../ricerche/2026-10-01-regole-deterministiche.md)):
  - **Uscita** (`wakeword.exit_intent`): solo la frase intera, a parte il nome e i
    riempitivi («allora», «ok», «grazie», «pure»…), con le storpiature misurate di «esci»
    («è sci», «Eshi», «Eschì», «Addio pesci!», «Cambio per pesci» con il nome in
    «Cambio»). `EXIT_WORDS` cercava «chiudi» ovunque: «Calliope, speni taverna» (01/10),
    «chiudi le tapparelle», «chiudi Excel» spegnevano il processo; `is_short_exit` prendeva
    «spegnilo», «senti», «ci riesci?», «alza audio», «Chiore sono». Sulle registrazioni
    tutte le 17 frasi d'uscita distinte restano uscite, i 2 falsi spariscono. **«Esci»,
    «arrivederci», «addio», «vai a dormire» addormentano**: storia e azione in sospeso si
    azzerano (`Brain.end_conversation`), niente finestra di follow-up, «A presto!». Solo
    **«spegniti»**, «spegni Calliope», «chiudi il programma» chiudono il processo («Mi
    spengo»). Addormentarsi è reversibile, quindi basta anche la prima frase («Calliope
    esci un attimo, facciamo una prova dopo»); spegnersi vuole la frase intera. Vale
    anche durante la registrazione della voce (annulla e dorme, o annulla e si spegne).
    **Da un satellite** (`audio_modo: satellite`, 02/10, `wakeword.exit_action`) anche
    «spegniti» addormenta soltanto e dice «Vado a dormire. Il server resta acceso: per
    spegnerlo usa calliope ferma.» (regola `uscita_spegni_satellite`): sulla DGX il processo
    è un servizio systemd che non riparte dopo un'uscita normale, e a voce non si riaccende.
  - **Stop** (`wakeword.is_stop`): tutte le parole della frase nel lessico di chiusura
    («grazie», «ok», «va bene così», «basta», «stop», «niente», «silenzio per favore»…), il
    nome escluso, da sveglia e dopo un'interruzione. «Ok, aprilo», «Ferma la musica»,
    «Ferma il timer», «Grazie, e domani che tempo fa?» vanno al modello. Con un'azione in
    sospeso («Lo apro?») anche «Grazie.» va al modello: il 01/10 era stato zittito.
    **Cortesia** (05/10, «ok, grazie» e «perfetto» restavano senza risposta):
    `wakeword.closing_kind` divide la chiusura intera in tre forme. Con una parola d'ordine
    di silenzio («basta», «stop», «zitta», «lascia stare», «niente», «fa lo stesso») resta
    muta come prima (`stop`, follow-up aperto); il ringraziamento («grazie», «ok, grazie»,
    «ti ringrazio», «gentilissima») e la conferma («perfetto», «ok», «va bene così»,
    «d'accordo») ricevono una frase breve senza il modello (`calliope/cortesia.py`: «Prego!»,
    «Figurati.», «Di niente.», «A disposizione.» / «Bene!», «Ottimo.», «D'accordo.», a
    rotazione, nel tono della persona o della casa: formale «Prego, è un piacere.»,
    computer di bordo «Ricevuto.»), sintetizzata all'avvio (`Speaker.prepare` →
    `say_cached`). Per la conferma una frase e non il suono di fine ascolto: quello c'è solo
    con `suoni_ascolto`, e «perfetto» resterebbe muto. Dopo, la storia resta (scambio
    breve, `Brain.record_courtesy`) ma la finestra di follow-up si chiude: fine dello
    scambio, il parlato della stanza dopo un «grazie» non si trascrive. «Ok», «va bene» dopo
    una risposta che finisce con «?» vanno al modello (`Brain.ultima_domanda`); azione in
    sospeso e barge-in invariati. «Sei.» e «Molto.» non sono chiusure. Regola `cortesia`.
  - **Approfondisci** (`DEEPEN_WORDS`): la frase intera; «controlla il volume», «verifica
    se la luce è accesa», «dimmi di più sul timer» vanno al modello. `SEARCH_PROMISE` non
    scatta sulle offerte («posso fare una ricerca») né sulle domande.
  - Correzioni minori: `agenda.cancel` annulla tutto solo con la richiesta intera
    («tutto», «tutti i promemoria»: «il promemoria di salutare tutti» li cancellava
    tutti e 3); il formato detto vale solo con «pdf», «excel», «word», «foglio di
    calcolo» non negati, e una lettera non è mai Excel («una lettera su un foglio
    intestato»); `parse_amount` usa «a 30» della frase solo se c'è un numero solo;
    «Mi chiamo Dario» dopo «Vuoi dirmi il tuo nome?» diventa «Dario» (`said_name`);
    `mentions_tool` si controlla prima di `clean_for_speech` (prima non scattava mai);
    tolte da `HALLUCINATIONS` le voci con il punto, mai confrontate.

- **Azione in sospeso** (01/10, `Brain.set_pending`, `PENDING_MSG`): un tool che chiude con
  una domanda di consenso mette nel risultato `in_sospeso` (tool, argomenti, cosa, domanda):
  documenti («Lo apro?», anche nell'annuncio in secondo piano), `pc_cerca_file` («Lo
  apro?», «Quale apro?» con i file numerati), guida della casa. Brain lo toglie dal
  risultato per il modello e, se la risposta detta finisce con «?», nel turno dopo lo mette
  come messaggio di sistema **dopo i ricordi**, subito prima della domanda; dal 04/10 vale 3
  turni della stessa persona (`azione_in_sospeso_turni`) e `azione_in_sospeso_s` (120 s), si
  toglie quando il tool proposto riesce (vedi «Conferme»). Decide il modello, nessuna regola «sì → apri». Misura con
  `stream_reply` vero (sessione del 01/10, ricordi davanti, 17 risposte × 3): con l'azione
  in sospeso 24/24 «sì» aprono e 27/27 «no» no, 0 «ho aperto» falsi; senza 12/24.

- **Rinominare chiede conferma** (02/10, `_rinomina_interlocutore`): Whisper sulla DGX ha
  trascritto «Calliope, chiamami Davio, ma vorrei sapere chi sono» e il modello ha rinominato
  subito il profilo di chi amministra. Ora la prima chiamata propone soltanto («Vuoi che ti
  chiami Davio d'ora in poi?», `risposta_finale` + `in_sospeso`, regola
  `rinomina_conferma` nel registro); il nome cambia solo se la stessa chiamata (stesso nome,
  stessa persona) arriva nella risposta **successiva** (`ToolContext.turno`), cioè se il
  modello giudica il «sì» un consenso. Il nome di un'altra persona registrata si rifiuta
  (`rename` ne avrebbe sovrascritto il profilo). Con Ollama (`prova_rinomina_ollama.py`,
  8 giri): la frase della DGX non rinomina mai, «sì» rinomina, «no» no; 1 volta su 3 al
  primo giro il modello diceva «Ho cambiato il modo in cui ti chiamo» senza richiamare il
  tool: `ACTION_CLAIM` ora prende anche «ho cambiato» e «ho rinominato», e dopo 40/40.
  **Cambio voce e registrazione restano senza conferma**: la voce nuova si sente subito e
  si torna indietro con una frase (effetto evidente e reversibile); la registrazione è già
  una procedura in più passi in cui la persona nuova deve parlare, e si annulla.

- **Correzioni dalle prove col 26B** (04/10, ramo `correzioni-26b`, log sulla DGX in
  `~/calliope-misure/modello26b/esiti/`): la rinomina non si confermava perché il 26B chiedeva
  «Vuoi davvero che ti chiami Davide?» **senza** il tool, e al «sì» la chiamata proponeva di
  nuovo: ora la domanda detta nella risposta subito prima vale come proposta
  (`builtin.domanda_rinomina`, regola `rinomina_domanda_detta`). La rete sulle azioni
  dichiarate vale anche dopo soli tool falliti o letture (`Brain._acted`: «Ho salvato…» dopo
  quattro `ricorda` falliti); `ricorda` senza memoria non dice più «non so chi sei».
  `appuntamenti_elenca` dice anche timer e promemoria; `archivio_cerca` con
  dato=descrizione dice numero e intestatari; l'estrazione dell'ufficio riceve la domanda di
  prima; `calliope_stato` su una capacità non segnalata dice che non c'è (Wikipedia =
  biblioteca); OCR, schede dell'archivio e testi dell'ufficio sullo stesso Ollama e modello
  della voce mandano `num_ctx` e `keep_alive` della voce (`agenti.impostazioni.opzioni_voce`).
  Con gemma4 e4b in locale: rinomina 3/3 giri, agenda tutto, ufficio 29/30, stato 34/34, banco
  80/84 (main 77/83), schermi 53/56 come main («Fammelo vedere sullo schermo» e «Mettimi sullo
  schermo i miei appuntamenti» restano deboli col 4B). Da rifare sul 26B.

- **Rete sulle azioni dichiarate** (01/10, `brain.ACTION_CLAIM`, `ClaimHold`,
  `CLAIM_NUDGE`): una risposta senza nessun tool nel turno che dice «ho aperto», «ho
  acceso», «ho spento», «ho creato», «ho impostato», «fatto…», «apro…» riceve **una**
  spinta. Il primo pezzo che il TTS direbbe (≥ 25 caratteri, come `split_sentences`) si
  trattiene finché non si sa se è una dichiarazione: se lo è non si dice e non entra nella
  storia (latenza invariata). Se la dichiarazione arriva più avanti ed è già stata detta,
  esce dalla storia quando la spinta porta al tool. Se dopo la spinta il modello dichiara
  di nuovo senza tool, si dice «Non ci sono riuscita: puoi ripetere la richiesta?». La
  spinta **non** mostra la frase trattenuta: con lei davanti, «Accendi la luce in taverna»
  ripetuto dopo lo stesso scambio dava 0/5 tool; senza 5/5. Casi del 01/10: «Ho aperto il
  documento "Disdetta Palestra.docx"» (due volte, finiva nella storia) e «Ho acceso le luci
  in taverna» a «TAVERNA». Non è una dichiarazione «il file che ho creato…» né «non l'ho
  aperto». **Né un ricordo** (02/10, `brain.is_claim`): dopo «chiudi taverna» →
  `casa_comando` vero, «Ho spento Taverna, quindi se intendi riaccenderla, posso…» veniva
  trattenuta e la risposta diventava «Ho bisogno di sapere il nome della stanza». Ora non
  scatta se la frase prosegue come ragionamento («quindi», «se intendi», «se vuoi», «visto
  che») **e** verbo e oggetto sono quelli di un tool riuscito nei turni prima
  (`Brain._recent_actions`: richiesta, tool, argomenti, conferma), o se la colloca nel
  passato («prima», «poco fa») e c'è un'azione prima. La dichiarazione nuda uguale
  all'azione vecchia resta una dichiarazione (il caso «TAVERNA»). Nel registro
  `dichiarata_ricordo`. Con Ollama la frase esatta non si riproduce (il modello chiede subito
  il nome); la rete scatta ancora, giusta, su «Ho abbassato la temperatura» detto a
  «Scendila».

- **Registro delle regole** (01/10): ogni turno ha `regole`, l'elenco delle regole sul testo
  scattate: `uscita_dormi`, `uscita_spegni`, `uscita_spegni_satellite`, `stop`, `stop_interruzione`, `cortesia`,
  `cortesia_dopo_nome`, `approfondisci`, `ricerca_promessa`, `annuncio_tool_taciuto` (solo l'annuncio di una chiamata; fino al 06/10 `nome_tool_taciuto`), `nome_tool_parlato` (dal 03/10 il nome di un tool detto a parole, «il mio comando per la casa»: prima la frase si taceva intera e Calliope restava muta),
  `citazione_tolta`, `nome_detto`, e da Brain e dai tool (`ToolContext.regole`,
  `note_rule`) `azione_in_sospeso`, `spinta_promessa`, `spinta_richiesta`,
  `spinta_dichiarata`, `dichiarata_taciuta`, `dichiarata_ricordo`, `riferimento_casa`,
  `textcallguard`, `conferma_al_posto_del_vuoto`,
  `agenda_tutto`, `formato_detto`, `lettera_non_excel`, `valore_assoluto_detto`,
  `casa_riscrittura`, `casa_delicata`, `casa_domanda_letta` (dall'08/10 anche `casa_nome_entita`, [casa](casa.md)); dal 02/10 `persona_io` e, dagli
  agenti, `lavori_permesso`, `lavori_senza_offerta`, `lavori_proposta_non_id`,
  `lavori_conferma_implicita` (dal 10/10 `lavori_conferma_diversa`, `sviluppo_cambio` e `sviluppo_analisi_prima`), `lavori_agente_irraggiungibile`; dal 03/10 `schermo_personale_senza_codice`, `schermo_personale_con_codice`, `schermo_proprietario_permesso`. Solo nomi: per gli ospiti il
  registro non tiene più dati di prima.

- **Ripetizioni come segnale di errore** (`revisione.py`): sulle registrazioni del 21 e
  24/09 la sola somiglianza del testo trova tutte le 12 coppie vere su 22 candidate. Come
  giudice gemma4:e4b è debole: con esempi ne conferma 9, di cui 6 giuste. Serve un
  segnale migliore, acustico (la confidenza di Whisper, oppure ritrascrivere la prima
  frase guidandola con la seconda) invece che testuale.

- **Un tool che fallisce può avvelenare la conversazione**: dopo un errore di `ricorda`
  («non so chi sei») il modello smetteva di chiamare tool e inventava ora e voci. Anche un
  messaggio di sistema che dice «non serve chiamare tool» lo fa. Formulare in positivo
  («per tutto il resto chiama i tool come sempre») e dare errori chiari. A metà
  conversazione «che voci hai?» resta debole: 1 su 3 chiama `elenca_voci`, le altre
  rispondono in modo vago, ma non inventano più nomi.

- **Frase d'attesa sui tool lenti** (26/09): se un tool ha `ToolSpec.announce` (oggi solo
  `biblioteca_cerca`), appena il modello lo chiama Calliope dice una frase breve
  («Vediamo.», «Un attimo, cerco.»), già sintetizzata all'avvio da `Speaker.prepare`. Copre
  la seconda passata dell'LLM: frase d'attesa a 0,4–1,0 s, risposta vera 0,45–0,55 s dopo.
  La sceglie il codice (`Brain.on_tool_start`), una volta per risposta, solo se Calliope
  non ha già parlato, e non entra nella storia. Il registro ha `primo_suono_s` e
  `prima_frase_s`. Non va messa sui tool veloci (ora, calcoli): sarebbe tempo perso.

- **Frase superflua prima della spinta** (01/10, `brain.TOOL_REQUEST`): «Calliope, apri il
  PDF della spesa» diceva «Non ho trovato alcun PDF…, potresti dirmi il nome?» e subito dopo
  «Ho trovato Lista della spesa, lo apro?». Con una richiesta di file o documento (ora anche
  lettere e tabelle) e il PC presente, tutto il testo della prima passata aspetta la fine:
  con un tool si dice, senza scatta la spinta e il testo non si dice né entra nella storia
  (`richiesta_trattenuta`). Le altre domande non cambiano: la prima frase esce prima che il
  modello finisca (prova a secco), mediane invariate su Ollama.

- **Modello davanti più forte** (03/10, [`docs/ricerche/2026-10-03-modello-davanti.md`](../ricerche/2026-10-03-modello-davanti.md)):
  sul banco dalle frasi vere (`prove/prova_regressione.py`, 116 turni) Gemma 4 26B-A4B NVFP4 su
  vLLM fa 112/116 contro 98–100 del 4B, senza chiamate scritte come testo, ma la prima frase è
  0,90 s di mediana e ~1,9 s al p90 (il 4B 0,48 / 1,33): genera a 29 token/s (esperti FP4,
  il resto BF16). **La DGX resta sul 4B.** *[Superato: almeno dal 06/10 la DGX usa
  `llm_profilo: gemma4-26b-ollama`, vedi [capacita-installazioni](capacita-installazioni.md).]* `gemma4:26b-a4b-it-qat` su Ollama (scaricato il
  03/10, profilo `gemma4-26b-ollama`, non attivato): 74–79 token/s, banco 110/116, prima
  frase 0,73 s (0,70 / 1,19 s a livello costante; ~2 s quando cambiava il livello di chi
  parla, prefisso nuovo: dal 03/10 i tool sono gli stessi per tutti e il salto non c'è più,
  vedi «Permessi dei tool»). Dal pomeriggio del 03/10 (§11 del rapporto) delega il codice
  (10/10, prima 1/10), e sulla DGX fa 143/144 con prima frase 0,68 / 1,18 s (4B 139/144,
  0,47 / 0,88): raccomandato, decide l'utente. Lo stesso giorno: il contesto del turno è
  «Dati del turno (non ripeterli…): persona: Dario…» perché il 4B lo ripeteva in testa alle
  risposte («Chi ti parla è Dario.», 17/32; ora 0/32, e `ContextEcho` toglie l'eco rimasta,
  regola `eco_contesto`); le richieste d'informazioni («parlami di…») vanno a
  `biblioteca_cerca` senza offerte; `llm_keep_alive` validato («-1» testo → -1; un 400
  all'avvio è un errore di configurazione). Le reti servono al 4B (senza: 67/116), non al 26B (stesso risultato,
  +0,04 s). Il modello di chat di Gemma 4 con il thinking spento non mette il canale vuoto
  dopo il risultato di un tool: il 26B a volte ragionava 10–18 s in silenzio (una volta 971
  s); corretto da `setup/linux/motore/gemma4_template.py`. Vincolare i tool (`required`) non
  cambia nulla sul 26B (40/40 anche con `auto`). Qwen3.6 come voce: il suo modello di chat
  rifiuta i messaggi di sistema a metà conversazione (i ricordi).

- **Comportamento della voce** (03/10, analisi del comportamento, ramo `comportamento`):
  - **Conversazione di una persona sola**: `Brain._check_conversation` chiude storia, azione
    in sospeso e riferimenti quando cambia chi parla (id del profilo; riconosciuto ↔ ospite)
    e dopo `storia_inattiva_s` (300 s); l'ospite che si faceva ripetere la password del wifi
    chiesta da Dario: 4/4 → 0/4, Dario che se la fa ripetere 4/4. Risultati dei tool
    riservati → traccia neutra, personali (agenda, promemoria, ricordi, chi parla) → solo la
    conferma, a fine risposta. L'azione in sospeso vale solo per chi ha sentito la domanda.
  - **Contesto del turno** (`TURN_CONTEXT_MSG`, primo prima della domanda): chi parla, e
    l'ora e la data «se ti chiedono l'ora o la data», poi «Per tutto il resto chiama i tool
    come sempre.». Il testo conta: l'ora detta come un fatto toglieva installa_proponi,
    calliope_stato e calcola (prova_stato_ollama 46/51 contro 50/51). Il prompt non dice
    più «sai chi ti parla solo dopo chi_parla». `ora_attuale` e `data_oggi` hanno `da_dire`.
    Le prove con «Che ore sono?» accettano l'ora giusta senza tool (`prove/ora_giusta.py`).
  - **Chiamata scritta in mezzo alla frase** («Ora sono ora_attuale.», c4e0f3d la diceva «il
    mio comando per l'ora»): `ToolNameHold` trattiene dalla frase con il nome di un tool;
    senza argomenti obbligatori (o con «nome(…)») si esegue (`chiamata_in_mezzo`), se no
    spinta (`spinta_nome_tool`), poi «Non ci sono riuscita…» (mai muta). Se la domanda è sui
    comandi («Che comando hai per le luci?») passa e main.py la dice a parole.
  - `ACTION_CLAIM` con i verbi dei tool e le forme senza «ho» («Timer avviato.», «Ricordato
    che…»), niente «non l'ho», niente passivi storici: 24/24 dichiarazioni (prima 4).
    `agenda.cancel` annulla solo con una parola vera in comune, altrimenti chiede quale.
    Promemoria nel passato rifiutati, durata vaga → «Quanto deve durare il timer?», `cambia`
    sconosciuto → errore; la ricerca promessa usa `Brain.stream_continuation` (niente «Cerca
    pure.» finto). Storia tagliata anche in token (`_trim_tokens`) e risultati vecchi ridotti
    (biblioteca, 12 domande: 15 952 → 11 257 token). `RETI` e `check_reti` in config.py: il
    profilo governa anche le reti di main.py, i profili del 26B tengono TextCallGuard. Prompt e
    descrizioni accorciati: prefisso DGX 6 650 → 5 820 token. Banco di regressione 112/130 →
    127/134 (casi nuovi: «Chi sono?» di Bianca, «Che comando hai per le luci?»).
  - Da guardare: «Ricorda che a Dario piace la pizza» (il nome di `ricorda` senza «_» scritto
    come testo) resta.
  - **Corretti il 04/10** (ramo `difetti-voce`, gemma4 e4b locale, banco di regressione 2 giri
    con 3 casi nuovi: 160/174 → 166/174, prima frase mediana 0,59 → 0,63 s nel rumore):
    risposta vuota dopo **sole letture** (`data_oggi`, `ora_attuale`…) → una seconda passata
    con `EMPTY_NUDGE` (regola e rete `vuoto_seconda_passata`), poi la conferma; dopo
    un'azione la conferma subito (vuota forzata dopo `data_oggi`: 10/15 risposte intere
    contro 0/9, +0,45 s di mediana, massimo 0,73). L'ora vecchia: il risultato di
    `ora_attuale` dei turni prima diventa `ora_di_allora` (`Brain._compact_old_results`);
    «No, intendevo che ore sono» 0/5 → 5/5 (nominare l'ora vecchia nel contesto del turno
    peggiorava). `ricorda` non salva un fatto non detto (`memory.unsaid_value`: i numeri
    detti nella conversazione, e su una domanda nessuna parola nuova; regola
    `ricordo_non_detto`, frase pronta «Questo non me l'hai mai detto…»): «47» salvato 2/2 → 0/2.
    «Un paio di minuti» = 2, «un paio d'ore» = 2 ore. «Su che hardware giri?» →
    `calliope_stato(cosa=macchina)` (`calliope/macchina.py`: modello del computer, sistema,
    processore, memoria, GPU dal registro o da /proc e /sys, modelli di voce, Whisper e
    agente, mai indirizzi, utenti o percorsi) 0/2 → 2/2, «che configurazione hai?» 2/2 col tool. `domanda_schermo` con ogni pronome
    («Me le dici?», «me la ridici?»).

- **Conversazione vera del 05/10 18:10** (DGX, 26B su Ollama, `stt_correzione` accesa; ramo
  `difetti-1810`, prova `prova_date_ricordi_ollama.py`). La correzione dello STT è sopra, in
  «Confronto STT…».
  - **Date**: a «sono nato il 4 luglio del 1977» il modello chiamava
    `calcola('2026-07-04-1977-07-04')` (zeri iniziali: errore) e poi `2026-1977`. Il 49 detto era
    giusto (compleanno di luglio già passato), ma per caso. Nuovo tool `data_calcola` (età, giorni
    mancanti o passati, giorno della settimana, distanza; date come dette, `tempi.parse_date`;
    `da_dire` con il soggetto, «Chi è nato il … oggi ha 49 anni; ne compie 50 il …»: con «49 anni
    compiuti» da solo e4b diceva «Ti sono 49 anni»); `calcola` con una data rimanda a lui. Scelto
    misurando con e4b (8 casi × 3 giri): prima 4/12 date giuste, funzioni di data dentro `calcola`
    23/24, tool a parte **24/24**; i conti senza date restano a `calcola`. La data di nascita non è
    stata salvata perché il 26B ha detto «Ho aggiornato il tuo profilo» senza chiamare `ricorda`
    (c'era solo `calcola`, una lettura) e «aggiornato» non era tra i verbi della rete.
  - **Stati inventati**: «Ricevuto, ordine sospeso.» e «Ho fermato tutto.» senza ordini né
    lavori. La rete sulle azioni dichiarate prende anche fermato, sospeso, interrotto, aggiornato,
    le cose «ordine», «profilo», «scheda», «estensione» e «ricevuto»/«d'accordo» davanti; contrari
    in `prova_testo` («Il treno si è fermato.», «La partita è stata sospesa…», «Ok, mi fermo.»).
    Con la frase del 26B come prima passata e gemma4: spinta, poi una risposta vera 4/4. Il ricordo
    di un fatto salvato non è una dichiarazione (`brain._recalls_fact`: «ho salvato che sei
    appassionato di…» a «cosa sai di me?», col tono amichevole finiva in «Non ci sono riuscita»
    2/2): solo se le parole piene e i numeri sono nei ricordi del turno.
  - **Ricordi fuori tema**: lo smoker in ogni risposta di fisica, la battuta ripetuta di turno in
    turno. `brain.MEMORY_USE`: i ricordi quando la domanda riguarda chi parla, i suoi gusti o un
    consiglio; altrimenti nemmeno come esempio o battuta. e4b il difetto lo fa poco: con la storia
    vera della DGX davanti 23/27 → 17/18, usati quando servono 18/18 come prima, perso «che
    argomento ti piacerebbe affrontare?» (0/6). Da riprovare col 26B.
  - Banco di regressione (e4b, giri alternati con main nella stessa cartella): 83 e 82/87 main,
    81 e 82/87 ramo, prima frase 0,62 contro 0,65 s; `data_calcola` ammesso per «che giorno era
    ieri?» e «domani». «Calliope, chi sono?» → «Calliope.» sbaglia anche su main dopo le 20:30
    (dipende dall'ora nel contesto del turno): da guardare a parte.
- **Giro 5 della prova e2e** (06/10, voce di Piper di Andrea):
  - «Calliope, spegniti.» trascritto «spenniti» (2 giri su 6; con faster-whisper «speniti» 3 e
    «spenniti» 1 su 8 sintesi): `speniti` e `spenniti` sono forme di «spegniti» in
    `wakeword._SHUTDOWN` (solo la frase intera); contrari «Spenti.», «spenniti la luce», «Speni
    la luce.», «Spendi meno.» in `prova_testo`.
  - `ACTION_CLAIM`: «Procedo con l'installazione.», «Procedo a scaricare…», «procedo all'…» sono
    dichiarazioni (un'azione annunciata in corso); non «Procedo?», «non procedo», né i verbi di
    lettura («procedo a elencare le voci», «con la ricerca»). La forma con «ho» non vale se la
    frase finisce con «?» senza pause: «Ti ho interrotto?» era spinta come dichiarazione e la
    risposta a «che ore sono?» diventava «Mi hai interrotta a metà frase»; «Ho acceso la luce,
    vuoi altro?» resta una dichiarazione.
  - Frasi del copione cambiate (rumore della voce sintetica, non difetti): «Spegnila, per
    favore.» (8/8 giusto con faster-whisper, «Spegnila.» 1/8) e «su che hardware stai girando?»
    (7/8, «su che hardware giri?» 2/8: «Succa arduo argili.»; con la trascrizione giusta il 26B
    chiamava `calliope_stato` 3 volte su 3).

## Tool senza argomenti, risposta «…», NOTIFY_SOCKET (06/10, DGX)

- **Chiamata senza nessun argomento obbligatorio** (`conversazione_cerca({})` dopo «Come più
  tardi.»): partivano la frase d'attesa «Fammi ricordare.» (a 5,0 s) e la ricerca. Ora
  `ToolRegistry.mancanti` dice gli argomenti `required` di una chiamata in cui **tutti** gli
  argomenti sono assenti o vuoti: Brain non dice la frase d'attesa e `call` risponde subito con
  l'errore («mancano argomenti obbligatori: domanda», regola `tool_argomenti_mancanti`), il
  modello richiama o risponde. Una chiamata con qualche argomento passa com'è: molti tool
  completano da soli (la proposta in sospeso di `delega_lavoro`, l'esercizio in corso di
  `compiti_aiuto`); il primo tentativo che controllava ogni argomento mancante rompeva
  `prova_minori` e `prova_conferma_unica`.
- **Risposta di sola punteggiatura** («…», «.»): la frase non va alla voce (`_frase_da_dire`) e
  Brain la tratta come vuota (regola `risposta_solo_punteggiatura`): la seconda passata con
  `EMPTY_NUDGE` anche senza una conferma pronta del tool e, se è di nuovo vuota, «Non ci sono
  riuscita: puoi ripetere la richiesta?» invece del silenzio. Contrario: una risposta vera dopo
  lo stesso tool non cambia.
- **NOTIFY_SOCKET**: nel journal «Got notification message from PID …, but reception only
  permitted for main PID» (10 volte dal 05/10: all'avvio, alla compressione, a
  `conversazione_cerca`). Era `systemctl show` (systemd 255, chiamato da `ollama_carico` per
  `OLLAMA_MAX_LOADED_MODELS`), che con NOTIFY_SOCKET nell'ambiente manda da sé «EXIT_STATUS=0»
  (misurato sulla DGX con un socket di prova; nvidia-smi no). L'unità ha già
  `NotifyAccess=main`: ora `main()` toglie la variabile dall'ambiente all'avvio
  (`trattieni_notify_socket`) e `notifica_systemd` usa il valore tenuto; nessun figlio (systemctl,
  ssh del tunnel, docker) la eredita. Prova in `prova_linux`.

## Risposte «vuote», testo nullo e persone di casa (07/10, DGX 06/10 sera, ramo `eta-vuoti`)

Dal registro dei turni e dal journal della DGX del 06/10 (18:48–18:53):
- **«testo: null» non era una frase vuota al modello**: erano frasi di un **ospite** (voce sotto
  soglia, 0,36), che il registro toglie per privacy; il console scrive «(una frase di un
  ospite)». Le frasi vuote davvero restano fuori (`esito: vuoto`, 18:49:40). Ora il registro
  tiene `testo_parole` e `risposta_parole` di un ospite (`TurnLog._write`), così null non è
  ambiguo.
- **«risposta: null» dopo `conversazione_cerca` e `anagrafica_cerca` non era il silenzio**: i
  due tool sono riservati e la risposta si toglie dal registro (`riservato: true`; nel journal
  «[prima frase 3.72s] …»). Ora resta `risposta_parole`.
- **`conversazione_cerca({})` non era una chiamata senza argomenti**: di un tool riservato il
  registro e il terminale scrivevano `{}` al posto degli argomenti. `tool_argomenti_mancanti`
  funzionava (i tool `*_cerca` hanno tutti `required`, ora controllato in `prova_eta_utenti`).
  Ora di un tool riservato restano i nomi degli argomenti dati, con «…» come valore.
- **Mai muta dopo una risposta vuota** (regola `vuoto_ripiego`): la risposta vuota del tutto
  dopo un tool fallito, dopo una lettura senza frase pronta o senza nessun tool, se non si è
  ancora detto niente, riceve la seconda passata (`EMPTY_NUDGE`, rete `vuoto_seconda_passata`) e,
  di nuovo vuota, «Non ci sono riuscita: puoi ripetere la richiesta?». Prima la seconda passata
  c'era solo con una conferma pronta o con la sola punteggiatura, e il resto finiva in silenzio.
  Contrario: già detto qualcosa nella stessa risposta, niente ripiego (`prova_brain`).
- **Utenti registrati e rubrica**: «Parliamo di Bianca, che cosa sai di lei?» → `anagrafica_cerca`
  (rubrica dell'ufficio); «è registrata, ma non ho ancora una sua voce associata» perché
  `elenca_utenti` dava `voce: null` (era la voce **di Calliope** scelta per lei). Ora
  `elenca_utenti` dà `impronta_voce` sì/no, `amministra`, `minorenne`, `voce_di_calliope` solo
  se scelta, età e compleanno a chi può saperli; le descrizioni di `elenca_utenti` (persone della
  casa) e `anagrafica_cerca` (clienti e fornitori) si rimandano. Misura con gemma4 e4b: «Bianca è
  registrata? Riconosci la sua voce?» 1/2 → 3/3; «che cosa sai di lei?» `anagrafica_cerca` 1/2 →
  0/3. Età e compleanni: [memoria-agenda-liste](memoria-agenda-liste.md).

## Dichiarazioni «inizio subito il lavoro» e proposte di altri (07/10, DGX)

- **Rete sulle dichiarazioni** (`brain.ACTION_CLAIM`, spinta `spinta_dichiarata`): dopo un «Sì,
  procedi.» attribuito a un'altra voce, nessun tool e la risposta «Perfetto, allora inizio subito
  il lavoro. Ti faccio sapere non appena ho finito.»; due minuti dopo `lavori_stato` → «Non ho
  lavori in corso». La rete non conosceva le azioni annunciate al presente: ora anche
  «inizio/comincio/avvio [subito] il lavoro (la ricerca, il programma…)», «parto/inizio/mi metto
  subito» a fine frase o con «a lavorarci», «lo affido/lo delego», «lo mando/passo all'agente».
  Contrari (in `prova_risultati.py`): «Inizio a capire…», «Ti avviso quando inizio il lavoro»,
  «Appena inizio il lavoro…», «Non inizio il lavoro senza il tuo sì», «Inizio io?», «Inizio
  subito il lavoro?», «Lo affido all'agente?», «Il lavoro lo affido a te», «L'inizio del
  lavoro…». Come le altre forme, solo nelle risposte senza tool.
- **Causa a monte**: il «sì» di chi non ha la proposta ha nei dati del turno la proposta
  dell'altra persona (`SOSPESO_ALTRUI_MSG`, regola `sospeso_altrui_consenso`): dettagli in
  [`sicurezza-politica.md`](sicurezza-politica.md). Così la risposta vera è «la proposta è di
  <nome>», e la spinta della rete non porta a un lavoro a nome di chi non l'ha chiesto (il tool
  rifiuterebbe comunque: l'offerta è della persona). Sonda con gemma4 e4b su questo portatile
  (proposta di Marta per una ricerca, poi «Sì, procedi.» di Luca con la voce incerta, 6–8 giri,
  agente finto): main «Cosa devo fare?» 6/6 (la conversazione di Marta si chiude e il modello non
  sa di cosa si parla; sulla DGX lo stesso vuoto è diventato «inizio subito il lavoro»), ramo
  «La proposta … è di Marta e solo lei può confermarla.» 8/8, nessun lavoro avviato. La prima
  forma del messaggio («non dire che la fai», senza dire cosa rispondere) dava 3 volte su 6 una
  domanda strana («Procedi con la proposta di Marta?»): ora il messaggio dice la frase da dire e
  «non fare domande».

## «Sì, grazie.» dopo «Procedo?» e «ho recuperato il dato» (07/10 pomeriggio, DGX, ramo `correzioni-giro7`)

Casi veri del satellite dello studio, profilo 26B (qui con nomi di fantasia).
- **«Sì, grazie.» perso**: «Fai una ricerca sui pannelli solari…» → `delega_lavoro` propone
  («…Procedo?»); «Sì, grazie.» (frase breve, voce 0,66) → nessun tool, «Prego! Sono qui se hai
  bisogno di altro.», e la richiesta va ripetuta. Non era il testo: `politica.consenso("Sì,
  grazie.")` era già vero e `closing_kind` non la prende (la cortesia scatta solo senza azione in
  sospeso, e «Grazie.» da solo con un'azione in sospeso va al modello, come voluto dal 01/10). Nel
  registro dei turni il turno era `conversazione: ospite, anonima`, senza `azione_in_sospeso`: il
  turno della richiesta era arrivato dopo una pausa lunga, la conversazione si era chiusa per tempo
  (`conversazione_scaduta`) e `end_conversation` l'aveva sostituita nel registro
  (`RegistroConversazioni.sostituita`), ma la **corsia** restava sulla vecchia; la frase breve
  continua solo la conversazione della corsia (`scegli`: `corsia.conv is c`) e finiva nella
  conversazione anonima del satellite, dove la proposta non c'era. Ora `sostituita` sposta anche
  la corsia che la stava usando (`conv` e `_in_uso`). Prova in `prova_corsie.py`
  (`prova_scaduta_sospeso`: senza la correzione 3 errori, `{'tipo': 'ospite', 'come': 'anonima'}`
  come sulla DGX; contrario: un ospite resta anonimo); in `prova_risultati.py` «Sì, grazie.» è un
  consenso, «No, grazie.» no, «Grazie.» resta cortesia. Misura con gemma4 e4b locale (3 giri,
  proposta finta di `delega_lavoro` con l'azione in sospeso): «Sì, grazie.» → `delega_lavoro`
  con `proposta=L1` **3/3**; «No, grazie.» → nessun lavoro 2/3 (il terzo: il modello non aveva
  proposto al primo turno).
- **«Ho appena recuperato il dato…» dopo tool falliti**: `data_calcola(persona=io)` fallito due
  volte, poi «Ho appena recuperato il dato che mi hai appena chiesto di ricordare: hai 49 anni.»
  (la rete `spinta_dichiarata` era scattata prima, su un'altra frase). Recuperare, calcolare,
  ricavare non erano dichiarazioni d'azione (sono letture). Ora, **solo quando in questa risposta
  ci sono tool e sono tutti falliti** (`Brain._solo_falliti`), anche «ho [appena] recuperato /
  calcolato / ricavato» è una dichiarazione falsa (`brain.FAILED_CLAIM`): la frase si trattiene e
  il modello riceve `FAILED_NUDGE` («i tool sono falliti… fai quello che dice cosa_fare»), una
  volta (regola `dichiarata_tool_fallito`); poi vale la regola di sempre. Senza tool è il ricordo
  della conversazione, dopo un tool riuscito è vera: in entrambi i casi si dice. «Ho trovato»
  resta fuori: «ho trovato nei tuoi ricordi il 4 luglio 1977» dopo il tool fallito è vero
  (misura). Prove in `prova_eta_utenti.py` e `prova_risultati.py` (Brain con `data_calcola`
  fallito e riuscito). La parte sui dati è in
  [`memoria-agenda-liste.md`](memoria-agenda-liste.md).
- Visto e non corretto: nel turno «Dovevi ricordarti…» la risposta è stata detta due volte di
  seguito (il modello, dopo la spinta su una dichiarazione già detta a metà risposta, ha ripetuto
  la stessa risposta). Da guardare se ricapita.

## Banco di regressione col 4B sceso (07/10 sera, ramo `regressione-4b`)

Il banco (`prove/prova_regressione.py`, gemma4 e4b locale, 2 giri) era 166/174 il 04/10, oggi
152/174 su main (ecf50d4) e 158/174 sul ramo del giro 9. Due cause, nessuna nel codice della voce:
- **Il finto dei lavori del banco era vecchio** (catena `conf`, `conf4`, `conf_tv`, 10–12 errori
  su 22): `LavoriFinto` prende `offerta` da `agenti.servizio.Lavori`, che dal 06/10 (ddc9498,
  lavori che sopravvivono a un riavvio) chiama `_interrotti_da_rifare`; il finto non l'aveva e
  ogni `delega_lavoro` finiva in `AttributeError`, da cui risposte su un lavoro mai proposto.
  Con il metodo (nessun interrotto) la catena torna 21/22. Non c'entra l'analisi della richiesta
  (`agenti/richiesta.py`): il finto non ha `analizzatore`, e il banco la salta come prima.
- **Ollama aggiornato da solo stamattina** (0.35.0 → 0.35.1, 07/10 08:33, `app-1.log`): il codice
  del 04/10 (18bb738, dal bundle della storia) oggi fa **162/174**, con gli stessi casi fissi di
  main: «Calliope, chi sono?» → «Calliope.», «Riesci a mostrarmi il documento sullo schermo?» →
  «devo sapere quale documento intendi» (nessun documento nella conversazione: la domanda è
  ragionevole), «Credo che tu abbia sbagliato l'ora.» → «posso controllare l'ora?» invece di
  `ora_attuale`, e «Scusa, io sono chi amministra.» → «Chi ti parla è Dario.» (eco). Né l'ora né
  la data del contesto del turno c'entrano (orologio finto alle 11:00 del 04/10: stessi errori),
  i pacchetti Python sono quelli del 04/10, il modello è lo stesso (digest ee6656371218).
  Ollama 0.35.0 non si è potuto riprovare (niente rete per scaricarlo): la causa è per esclusione.
- Dopo la correzione del finto: **165/174** (contro 162 del codice del 04/10 nelle stesse
  condizioni), prima frase mediana 0,69 s, p90 1,20 s. Restano i quattro casi sopra (il 4B, non
  la voce della DGX, che è il 26B) e la variabilità di sempre (`info3`, `ora_vecchia`).

## Rete `spinta_esercizi` (08/10, ramo `esercizi-pilota`)

Con un esercizio in sospeso (tool `esercizi`, calliope/esercizi/) una risposta del modello senza
il tool si trattiene e il modello riceve una spinta (`ESERCIZI_NUDGE`), una volta; poi la sua
risposta si dice. Caso: col 4B, a «Verbo.» la risposta era «Perfetto! Prossima: …» copiata
dalla storia, cioè la correzione decisa dal modello (italiano 11/18 nel banco); con la rete
35/36 e matematica 36/36 (`prova_esercizi_ollama`, 2 giri). Categoria «modello» in `RETI`
(`Brain`: `turn_pending_tool == "esercizi"` attiva lo stesso trattenimento di
`spinta_richiesta`). Prova con backend finto e contrario in `prova_esercizi`. Dettagli in
[minori](minori.md) e [`../ricerche/2026-10-08-esercizi.md`](../ricerche/2026-10-08-esercizi.md).

## La forma degli argomenti, l'estensione nominata, la risposta interrotta nel registro (08/10, ramo `correzioni-giro10`)

Dal caso vero della DGX del 07/10 sera (meteo per città, vedi
[agenti-estensioni](agenti-estensioni.md)):
- **`ToolSpec.prepara`** (nuovo, `tools/spec.py`, applicato da `ToolRegistry.call` prima dei
  permessi e della politica): la forma degli argomenti scelti dal modello ricondotta a quella del
  tool, `(ctx, argomenti) → argomenti`. Solo conversioni di forma (principio 10), con la loro
  regola nel registro. Il primo è `estensioni_gestisci` («attiva» → `approva` o `riattiva`,
  `estensioni_azione_sinonimo`): prima la politica chiedeva «vuoi che faccia «attiva»…?» e al «sì»
  il tool diceva «azione sconosciuta».
- **Dati del turno `EST_NOMINATA_MSG`** (rete `estensione_nominata`, categoria modello, regola
  `estensione_nominata`): la frase nomina un'estensione attiva → il suo tool, cosa fa e l'input,
  subito prima della domanda come `LAVORO_MSG`; mai nel prompt di sistema (prefisso in cache).
  Riconoscere il nome è una regola sul testo: è ammessa perché il suo effetto è solo un contesto
  del turno, e ha i contrari in `prove/prova_estensioni_versioni.py`.
- **Registro dei turni di una risposta interrotta**: alle 18:48:50 «Com'è andata l'estensione?» →
  `lavori_stato` aveva risposto (nel journal la frase c'è), ma «risposta» nel registro era vuota.
  Non era un errore del tool: dopo un barge-in «risposta» tiene solo le frasi **sentite per
  intero** (`speaker.played`), e la risposta di `lavori_stato` è una frase sola, lunga, interrotta
  dal nome a metà (lo stesso alle 18:48:38 e alle 18:54:36). Ora resta così, e c'è anche
  **`risposta_inviata`**: quello che era già andato alla voce, ripulito come la risposta (codice
  dello schermo, testo scritto oscurato, parole della frase di sfida); per un ospite nullo come
  la risposta. Prima la «risposta» dopo un'interruzione non passava nemmeno dalla pulizia
  (`Ciclo._ripulisci_per_registro`).

## Modalità sviluppo nei dati del turno (08/10, ramo `modalita-sviluppo`)

La modalità sviluppo ([agenti-estensioni](agenti-estensioni.md#modalità-sviluppo-0810-ramo-modalita-sviluppo))
arriva al modello come **dati del turno**, mai nel prompt di sistema (il prefisso non cambia):
`Sviluppi.dati_turno` → `SVILUPPO_MSG` in `calliope/sviluppo.py`, messo da `Brain._sviluppo_turno`
dopo l'estensione nominata (regola `sviluppo_modalita`, rete spegnibile `modalita_sviluppo`): cosa
si sviluppa, la fase («siamo al collaudo (3 di 5): fatte analisi e sviluppo e test; mancano
revisione e attivazione»), la specifica, la riga della fase (`riga_fase`: cosa si fa adesso e con
quale tool), il ritorno all'analisi, il fuori tema e «niente sviluppi nuovi». Senza uno sviluppo
aperto, gli sviluppi sospesi solo se la frase parla di riprendere o di sviluppo (`SOSPESI_MSG`).
Un contesto, non un ordine (principio 10).

In coda alla risposta, dal codice (`Brain._sviluppo_coda`, mai dopo una domanda, che deve restare
l'ultima cosa detta):
- **`sviluppo_riga_fuori_tema`**: con uno sviluppo aperto, dopo una risposta che ha usato solo tool
  d'altro e non ne parla («svilupp», «collaud», «estension»… o il titolo), «Intanto restiamo sullo
  sviluppo di «…»: siamo al collaudo.». Nella misura con gemma4 la riga l'ha sempre scritta il
  modello da sé («Ricorda che stiamo collaudando l'estensione…»): è una rete.
- **`sviluppo_promemoria_giorno`**: una volta al giorno, alla prima risposta a chi amministra, gli
  sviluppi sospesi («A proposito: lo sviluppo di «…» è sospeso, eravamo al collaudo. Quando vuoi,
  dimmi «riprendiamo lo sviluppo di …».»).

## Modalità sviluppo, versione 2: nomi dei tool e righe di fase (08/10, ramo `modalita-sviluppo-2`)

Nomi nuovi dei tool dei lavori e dello sviluppo (nome singolare + verbo, prefisso per famiglia:
`lavoro_affida`, `lavoro_stato`, `lavoro_risultato`, `lavoro_rispondi`, `lavoro_annulla`,
`programma_esegui`, `sviluppo_apri`, `sviluppo_passo`, `sviluppo_collauda`, `sviluppo_chiedi`,
`sviluppo_correggi`, `estensione_gestisci`; le voci qui sopra hanno i nomi di prima), con le
misure prima e dopo in [agenti-estensioni](agenti-estensioni.md#modalità-sviluppo-versione-2-0810-ramo-modalita-sviluppo-2).
Il prompt dei lavori dice che il codice e le funzioni permanenti sono `sviluppo_apri`. Nei dati
del turno (`SVILUPPO_MSG`) al collaudo e alla revisione: «perché?» → `sviluppo_chiedi`,
«correggilo» → `sviluppo_correggi`; allo sviluppo fermo a una tappa le tre scelte; per fermarsi
«chiudi (chiede conferma)». Regole nuove nel registro: `tool_nome_vecchio`,
`lavoro_codice_sviluppo`, `sviluppo_apertura`, `sviluppo_collaudo_fallito`, `sviluppo_chiedi`,
`sviluppo_chiedi_guasto`, `sviluppo_correzione`, `sviluppo_chiudi_conferma`,
`sviluppo_chiudi_sospende`, `sviluppo_tappa_continua`, `sviluppo_tappa_cambia`,
`sviluppo_correggi_nuovo`; «chiamata_» davanti al nome di un tool è un prefisso per `TextCallGuard`
come «call_».

## Spiegazioni inventate su sé stessa (08/10 sera, ramo `conversazioni-cronologiche`)

**Caso vero della DGX** (08/10 17:43, 26B): dopo tre ricerche nelle conversazioni passate,
«Come mai secondo te non sei riuscita a recuperare queste informazioni…? Forse c'è un buco?» →
«non è che non le abbia recuperate, è che ho dovuto fare un piccolo lavoro di ricerca nei
nostri vecchi scambi per essere sicura di non inventarmi nulla»: falso, la ricerca per
somiglianza aveva trovato a caso (il modo cronologico è in
[contesto-conversazione](contesto-conversazione.md)).

**Fatto**: una spinta nel prompt di sistema, dopo la frase sulla memoria: «Se ti chiedono perché
hai risposto così o perché qualcosa non è andato, non inventare spiegazioni sul tuo
funzionamento: racconta con parole semplici cosa hai fatto davvero in questa conversazione,
oppure di' che non lo sai. Per tutto il resto chiama i tool come sempre.» Nel prompt di sistema
e non nei dati del turno: la domanda non si riconosce dal testo (principio 10), e la storia ha
già le chiamate dei tool (i risultati riservati come traccia neutra).

**Misure** (gemma4 e4b, `prove/prova_conversazioni_ollama.py`, 3 giri, due storie: la sequenza
cronologica e il caso vero):
- **Senza la spinta** (12 risposte in due misure): 11 con una giustificazione inventata («è un
  modo per assicurarmi di darti la risposta più accurata», «non ho dimenticato nulla di ciò che
  mi hai detto»), 9 con `calliope_stato` chiamato e la sua frase attaccata in fondo.
- **Prima versione** («…di' cosa hai fatto davvero in questa conversazione (i tool chiamati e
  cosa hanno risposto) o che non lo sai»): il modello nominava il tool («usando il tool
  conversazion…»), la rete `nome_tool_parlato` lo fermava e restava «Non ci sono riuscita: puoi
  ripetere la richiesta?» (3/6).
- **Senza «Per tutto il resto chiama i tool come sempre»**: «Ma noi non avevamo parlato anche
  del tokamak?» in una conversazione nuova non cercava più (1/8 contro 7/8 senza la spinta, e
  7/8 con la frase finale): come per la modalità e i dati del turno, un «non fare» nel prompt
  spegne i tool se non si ridice di chiamarli.
- **Versione finale**: 6/6 raccontano cosa hanno fatto («Ho cercato di recuperare le
  conversazioni passate usando lo strumento apposito, ma non ho trovato un riepilogo
  immediato»), nessuna giustificazione inventata, nessun `calliope_stato`; resta qualche frase
  generica («non ho un accesso diretto e immediato a tutti i nostri scambi»). «Perché il cielo è
  blu?» 3/3 con la spiegazione vera; `prova_brain_ollama` uguale. Da rifare col 26B sulla DGX.

## Argomenti incerti nel registro e «forse intendeva» (08/10, ramo `parole-incerte-f01`)

F0 e F1 di [`../ricerche/2026-10-08-parole-incerte.md`](../ricerche/2026-10-08-parole-incerte.md);
probabilità, vocabolario e misure in [stt-tts](stt-tts.md).

- **Registro dei turni**: campo `stt_argomento`, una voce per argomento marcato di ogni chiamata:
  tool, argomento, tipo, esito (`pieno`, `vuoto`, `errore`, `fermato`), valore (già nel registro
  come argomento del tool), nome noto più vicino e somiglianza (`e_noto` se è proprio quello),
  `p_min`/`p_media`/`parole` e `uguale_alla_frase` (o `allineato: false`, `p_tardi`), `stt_ms`,
  `correzione`, `forse`, `da_suggerimento`. Per ospiti e zona grigia solo numeri (né valore né nome
  noto) e mai F1; per un tool riservato mai il valore; scritto da uno schermo: oscurato come i tool.
  Riassunto in `calliope stato --turni` (chiamate, esiti, probabilità sotto 0,3/0,4/0,5 anche
  sugli esiti vuoti, nomi vicini, correzioni spontanee e quelle riuscite dopo un vuoto,
  suggerimenti e quanti usati).
- **Regole** (principio 10): `correzione_argomento` è solo misura (lo stesso tool entro tre turni
  con un valore quasi uguale, ≥ 0,75 con le doppie, numeri uguali); `argomento_forse` è un dato del
  turno nel risultato del tool, mai un cambio del valore (rete `argomento_forse`, categoria
  «modello», spegnibile con `llm_reti_spente`); `argomento_forse_usato` quando la chiamata dopo
  usa il nome suggerito. Il riconoscimento dell'esito vuoto guarda il risultato del tool, non la
  frase della persona.
- **Quando no**: esito pieno, errore o fermato; ospite o zona grigia; risposta a una sfida; il
  valore era già il nome suggerito (il «sì» che non trova di nuovo non riceve un altro «forse»);
  un'altra domanda già fatta in questa risposta (un tool con la sua proposta); il tool ha già i suoi
  nomi vicini (la casa, `nomi_vicini`) o una frase pronta (`risposta_finale`); frase scritta senza
  nome vicino (niente Whisper da cui dubitare).
- **Politica**: il «sì» passa dalla proposta in sospeso (`set_pending`, solo se la risposta finisce
  con «?»), con gli stessi argomenti: nessuna domanda in più (`politica_conferma_unica` nella prova
  del collaudo). Se il modello richiama con gli argomenti in un'altra forma (`argomenti` invece di
  `dati`) la politica chiede come sempre: non si allenta la provenienza per F1.

## Il «no» alla proposta e il «sì» che passa ad altro (09/10, ramo `intento-no`)

Regole nuove sul testo (principio 10), descritte con il caso vero e le misure in
[sicurezza-politica](sicurezza-politica.md): `proposta_rifiutata` (un «no» in testa chiude la
proposta e la sfida), `rifiuto_nei_dati` (dati del turno `RIFIUTO_MSG` finché la conversazione
resta aperta), `politica_proposta_rifiutata` e `rifiuto_superato` (la politica non richiama il
tool rifiutato per lo stesso bersaglio finché la persona non lo chiede con le parole del tool),
`consenso_avversativo` («Sì, però ascolta…» non è un consenso). Contrari in `prove/prova_testo.py`.

## La compagnia e il giudizio «rivolta a Calliope» (09/10, ramo `compagnia`)

Più voci vicino allo stesso satellite (dettagli in [stt-tts](stt-tts.md)). Regole nuove nel campo
`regole` del registro: `voci_compagnia`, `compagnia_nome`, `compagnia_senza_breve`,
`compagnia_voce_nella_frase`, `pericolo_compagnia`, `non_rivolta_ombra`, `non_rivolta`. Sono regole
sull'audio e sulla voce (ciò che il modello non vede, principio 10); il significato della frase lo
decide il modello:

- **F2, «la frase è rivolta a Calliope?»** (`calliope/rivolta.py`): solo in compagnia, solo sulle
  frasi senza il nome dentro la finestra d'ascolto (mai con il nome, dopo il nome da solo, scritte,
  con una persona sola). Giudizio separato con l'output strutturato `{"per_calliope": bool}` sul
  modello del rilevatore di pericolo (`compagnia_rivolta_modello` vuoto), in un thread in parallelo
  alla risposta; nel contesto gli ultimi scambi con il **nome di chi ha la conversazione**
  (`rivolta.etichetta`), mai la voce. `compagnia_rivolta: ombra` (predefinito): `rivolta` nel
  registro e la regola `non_rivolta_ombra`, Calliope risponde come prima. `attiva`: il giudizio si
  aspetta solo prima della prima frase, della frase d'attesa e dei tool (`Brain.prima_del_tool`);
  non rivolta → silenzio, lo stream del modello si chiude, nessuna finestra nuova, niente testo
  nel registro, la frase e la risposta taciuta escono dalla storia (`Brain.dimentica_ultimo_turno`;
  esito `non_rivolta`). Una protezione si dice sempre. Guasto o oltre
  `compagnia_rivolta_timeout_s` (2 s) = rivolta.
- **Misura col modello** (`prove/prova_rivolta_ollama.py`, nel runner `--ollama`; gemma4 e4b sul
  portatile, 56 frasi di fantasia, due giri uguali): 26/27 rivolte e 27/29 non rivolte giuste,
  mediana 287 ms, p90 295 ms (soglie 25 e 26). Con «Persona» al posto del nome nel contesto 27/27 e
  24/29 (sotto soglia: «Questa era terribile, Marco.», «Chiedile se domani piove…»): per questo il
  nome. Sbaglia ancora «Che ne pensi dei cani?» (detto dall'ospite a Calliope), «Dille alle sette…»
  e «Ok.». Da accendere dopo qualche giorno di ombra sulla DGX, letti i `non_rivolta_ombra`.

## Il dialogo tra tool e modello: errori in parole e giri di correzione (09/10, ramo `dialogo-tool`)

Caso vero della DGX (09/10 08:19–08:20): «Raccontami le ultime novità della giornata» →
`web_cerca({'tipo': 'notizie'})` → la traccia del `TypeError` («_web_cerca() missing 1 required
positional argument: 'domanda'») → «ho avuto un piccolo intoppo, riprovo subito» senza
riprovare, quattro volte. Decisione di Dario: nessuna regola per il caso, un protocollo
generale. Progetto e misure: [`../ricerche/2026-10-09-dialogo-tool.md`](../ricerche/2026-10-09-dialogo-tool.md).
- **Errori come messaggi per il modello** (`calliope/tools/dialogo.py`, in `ToolRegistry.call`
  per ogni tool, estensioni comprese): gli argomenti contro lo schema e la firma prima della
  chiamata (obbligatorio assente o vuoto che la funzione non completa da sé, argomento
  sconosciuto); l'errore dice quale argomento, tipo, valori ammessi, la sua descrizione (dallo
  schema o dalla descrizione del tool), un esempio con la chiamata del modello completata, la
  frase della persona e `cosa_fare` (richiamare con le sue parole; chiedere solo se non c'è
  niente che serva), `correggibile: true`. Eccezioni dei tool senza traccia
  (`tool_errore_interno`: un errore di programmazione non è correggibile, un `ValueError` sì);
  `{errore}` senza `ok` uniformato. Conversioni di forma (`tool_argomento_forma`: maiuscole,
  accenti, un solo valore ammesso che comincia così, numeri e vero/falso come testo); un
  valore fuori dai valori ammessi **non** è un errore (decide il tool: «stop», cambia
  «nessuno»… avevano già le loro risposte e le loro prove). `ToolRegistry.mancanti` dice ora
  tutti gli argomenti che fermano la chiamata (niente frase d'attesa per una chiamata che non
  parte). Regole: `tool_argomenti_mancanti` (com'era), `tool_argomenti_non_validi`. L'errore
  del registro non porta dati: fuori dalla busta dei dati non fidati
  (`ToolContext.errore_registro`, regola `fallito_senza_dato`).
- **Giro di correzione in Brain**: `last_tools` segna `correggibile`. Dopo un errore
  correggibile il testo della passata aspetta la fine; senza chiamata non si dice e il modello
  riceve `CORREZIONE_NUDGE` (regola `correzione_tool`, rete del modello `correzione_tool`). Una
  domanda alla persona si dice dal secondo giro (al primo il 4B chiedeva il dato appena
  detto). Tetto `tool_correzioni_max` (2) dentro `max_tool_turns`; un errore non correggibile
  non trattiene niente. Prima, le spinte sulle promesse valevano solo senza nessun tool nella
  risposta, e «riprovo subito» dopo un tool fallito passava.
- **La persona aggiornata**: oltre `tool_correzione_avviso_s` (2 s) dall'inizio della risposta
  senza aver detto niente, una frase di `dialogo.FRASI_CORREZIONE` («Un attimo, sistemo la
  richiesta.»), una volta, dalle frasi d'attesa (`announcements`, sintetizzate all'avvio).
- **Misura** (gemma4 e4b locale, prima passata forzata con la chiamata sbagliata, 3 giri):
  corrette 18/21 contro 2/21 di main (notizie, Ansa, meteo con `query`, timer, promemoria,
  calcola 3/3; lista 0/3: il 4B chiede «Cosa vuoi aggiungere?»); contrari giusti (dato non
  deducibile → domanda; errore interno → detto, nessun giro). Ogni giro 0,4–0,7 s col 4B.
  Prova a secco `prove/prova_dialogo_tool.py` (la chiamata vuota a ognuno dei 42 tool con
  argomenti obbligatori). Da guardare sulla DGX: `correzione_tool` e `correzione_avviso` nel
  registro dei turni, e se il 26B risolve la lista.

## Domande su di sé: chi sei, novità, versione (09/10, ramo `stato-novita`)

Caso vero della DGX (09/10 mattina): alle «ultime novità sul tuo aggiornamento» Calliope ha letto
l'elenco intero delle capacità, poi ha inventato «non ho un registro delle versioni» e «il mio
codice è distribuito su diversi server». Accanto alla spinta dell'08/10 («non inventare
spiegazioni sul tuo funzionamento»), la frase del prompt sulle capacità
(`capacita.testo_prompt`) manda a `calliope_stato` anche «cosa sai fare con la casa?» e le
domande su di sé (chi sei, dove giri, chi ti ha fatta, che versione sei, cosa c'è di nuovo):
`cosa=novita` (con `periodo`), `cosa=chi_sei`, `area`. Le risposte sono frasi pronte dal codice
(`risposta_finale`): fatti letti da CHANGELOG.md, dal gestore e dall'inventario della macchina.
Regola nuova `stato_periodo_novita` (solo `periodo` → novità), con il contrario. Dettagli e
misure (29/32 con gemma4 e4b sul portatile): [capacita-installazioni](capacita-installazioni.md).

## Approfondire dopo una ricerca (09/10, ramo `approfondisci-notizie`)

Caso vero della DGX (09/10, 10:21, 26B): «Prendevo le ultime notizie, altre news» → `web_cerca`
(notizie) → «Secondo l'ANSA, le condizioni di salute del re … Ci sono anche notizie sulle
proteste … e sul festival …». Poi «Approfondiamo le condizioni reale.» (= «del re»): regola
`approfondisci` scattata, nessun tool, e «Mi spiace, ma non ho informazioni più dettagliate…
oltre a quelle che ti ho appena riportato». Falso: poteva cercare.

Perché: la regola `approfondisci` (`ciclo._contesto_e_allegati`, `DEEPEN_WORDS`) cercava nella
biblioteca **la frase del turno prima** («Si, prendevo con le ultime notizie altre news…», campo
`approfondimento` del registro), trovava passaggi fuori tema e passava al modello «rispondi con
questi passaggi… se non contengono la risposta dillo, senza inventare». Il modello ha eseguito
l'istruzione. In più il testo dei siti esce dalla storia a risposta finita (`WEB_TOLTO`): il
modello vede solo ciò che ha detto e crede di non avere altro.

Correzione generale, non per il singolo caso (decide il modello, il sistema gli dà il contesto):
- **Dati del turno `RICERCA_MSG`** (`brain.py`, rete `ricerca_recente`, categoria «modello»):
  se in uno dei due turni prima c'è una ricerca (`web_cerca` o `biblioteca_cerca`), il modello
  riceve tool e domanda dell'ultima ricerca (*storico: dal 09/10 sera le ricerche dei sei turni
  prima con la loro fonte, sezione seguente*) e l'indicazione: per approfondire, dire di più o
  rispondere su una delle cose riferite, chiamare di nuovo quel tool con una domanda mirata, con
  i nomi detti; se la persona parla d'altro, la riga non conta. Non guarda la frase: vale anche
  per «dimmi di più sul festival» o «e le condizioni del re?», che `DEEPEN_WORDS` non prende.
  Regola `ricerca_recente`. Se quella ricerca adesso non c'è (senza rete, livello che non la
  può usare): `RICERCA_SPENTA_MSG`, dire onestamente che non si può cercare, regola
  `ricerca_recente_spenta`.
- **Spinta `spinta_ricerca`** (`RICERCA_NUDGE`, stessa rete): dopo una ricerca, un «non ho altre
  informazioni» senza aver chiamato tool in questa risposta non si dice né entra nella storia; il
  modello riceve la spinta a cercare, una volta (poi la sua risposta si dice). Usa `ClaimHold`
  come `spinta_archivio` (e prima di lei); `NON_SO` ora prende anche «altre/ulteriori
  informazioni», «dettagli», «notizie», «aggiornamenti» (casi in `prova_testo`).
- **`approfondisci` non rifà la biblioteca dopo una ricerca**: con una ricerca nei due turni prima
  (`Brain.ricerca_recente`) il ciclo lascia la frase al modello con i dati del turno (regola
  `approfondisci_al_modello`). Dopo una risposta a memoria resta com'era (il Tevere del 26/09).

Misura (portatile, gemma4 e4b, SearXNG finto, `prove/prova_ricerca_seguito_ollama.py 2`): «prima»
(rete spenta e biblioteca con la domanda di prima) seguiti 8/8, contrari 4/6; «dopo» seguiti 8/8,
contrari 6/6. Il 4B cercava già da solo anche «prima»: il guasto del caso vero è del 26B, da
riprovare sulla DGX. Il «prima» sbagliava con internet spento (biblioteca e «venti mostre» dal
risultato vecchio); il «dopo» dice «adesso non riesco a raggiungere internet». Prima frase
1,7–2,0 s in tutti e due. Limite visto: senza rete (`online` falso) `web_cerca` esce dall'elenco
ma il modello lo chiama lo stesso dalla storia e il registro lo esegue (qui fallisce con la frase
pronta: onesto, ma il tool non dovrebbe partire).

## Le ricerche della conversazione con la loro fonte (09/10 sera, ramo `sera-ricerca`)

Caso vero della DGX (09/10, 21:04–21:06, 26B): notizie della tromba marina nel Trapanese con
`web_cerca` tipo notizie, poi «Metti un timer di 5 minuti», «Che ore sono?», «Dimmi qualcosa
sulla torre di Pisa» (`biblioteca_cerca`), poi «Torniamo alla notizia del trapanese di prima.
Dimmi di più.» → `biblioteca_cerca("tromba marina Marsala danni feriti")` e una risposta vaga
sulla tromba marina in generale. `RICERCA_MSG` diceva solo l'ultima ricerca (la biblioteca), e
solo nei due turni prima.

- **`RICERCA_MSG` con l'elenco** (`brain.py`, `Brain.ricerche_conversazione`): le ricerche
  (`web_cerca`, `biblioteca_cerca`) degli ultimi `RICERCA_TURNI_ELENCO` (6) turni, dalla più
  recente, una per argomento e fonte, al più `RICERCA_ELENCO_MAX` (4), compatte: «in questa
  conversazione hai cercato (dalla più recente) «torre di Pisa» con biblioteca_cerca; «tromba
  marina Trapanese» con web_cerca tipo notizie; «ultime notizie» con web_cerca tipo notizie»; se
  chi parla torna a una di queste, richiamare il tool di quell'argomento (le notizie con tipo
  notizie). Una fonte che adesso non c'è è segnata «(adesso non disponibile)». Con tutti e due i
  tool c'è anche il criterio per una ricerca nuova (`RICERCA_CRITERIO`): biblioteca per i fatti da
  enciclopedia, internet per guide pratiche, consigli, prodotti e cose recenti. Restano dati del
  turno: decide il modello (principio 10), «se parla d'altro questa riga non conta».
- **La spinta resta stretta**: `spinta_ricerca` («non ho altre informazioni» senza cercare) e
  `Brain.ricerca_recente` (il ciclo che non rifà la biblioteca per «approfondisci») valgono solo
  con una ricerca nei due turni prima (regola `ricerca_recente`); dal terzo al sesto turno solo
  l'elenco (regola `ricerca_elenco`). Con l'ultima ricerca dei due turni prima non disponibile
  resta `RICERCA_SPENTA_MSG`.
- *Storico (09/10 sera):* nella sezione «Approfondire dopo una ricerca» qui sopra, «tool e domanda
  dell'ultima ricerca» nei due turni prima: ora l'elenco dei sei turni.
- **Il criterio anche nei tool**: la descrizione di `web_cerca` nomina guide pratiche, consigli e
  prodotti; quella di `biblioteca_cerca` dice che non serve per quelli; il risultato della
  biblioteca con passaggi fuori tema, con la ricerca su internet disponibile, aggiunge «se la
  domanda è pratica o su cose recenti e i passaggi non rispondono, cerca con web_cerca» (caso
  vero delle 18:47: tre `biblioteca_cerca` per la birra fatta in casa, passaggi su un film di
  Chaplin). Rete `ricerca_recente` (descrizione aggiornata).
- **Misura** (`prove/misura_ricerche_fonte.py 3`, gemma4 e4b sul portatile, SearXNG e biblioteca
  finti; «prima» col codice di main): «torniamo alla notizia del trapanese» → `web_cerca` sulla
  tromba marina 3/3 prima e 3/3 dopo (il 4B ci arrivava già: da riguardare col 26B sulla DGX);
  la birra fatta in casa → `web_cerca` **0/3 prima, 3/3 dopo**. Prima frase mediana del seguito
  2,9 s prima, 2,0 s dopo (rumore: stesse chiamate).
- Prove a secco in `prova_web` (6b aggiornata, 6c nuova: l'elenco con le fonti, l'ordine, i
  turni, il criterio solo con tutti e due i tool, la stessa ricerca una volta sola, le
  precedenze qui sotto).
- **Precedenze fra i dati del turno** (dall'analisi delle regole del 09/10, § 3.10, coppie
  `RICERCA_MSG` contro `ARCHIVIO_NOTA` ed `EST_NOMINATA_MSG` contro `RICERCA_MSG`): con le
  ricerche nei dati del turno, dopo la ricerca automatica nell'archivio (`spinta_archivio`) la nota
  è `ARCHIVIO_NOTA_RICERCHE`: risultati dell'archivio, se non c'entrano e la domanda riguarda una
  delle ricerche di prima si richiama quel tool, «non lo so» solo dopo; senza ricerche resta
  `ARCHIVIO_NOTA`. Con un'estensione nominata nella frase la riga delle ricerche finisce con
  `RICERCA_EST` («vale la riga dell'estensione, non queste ricerche»). Un solo ordine, scritto.

## La città della casa e le estensioni nel prompt (09/10, ramo `citta-casa-notizie`)

Caso vero della DGX (09/10, 10:30): «Che tempo fa?» → `web_cerca` generico → «Non so
esattamente dove ti trovi… se mi dici la tua città», con l'estensione «Meteo città» attiva
(città, giorni, paese). Principio di Dario: niente regole per il singolo caso, un contesto
chiaro e il modello decide.

- **`casa_citta`** (configurazione nuova, sezione `casa`): la città o il paese della casa, mai
  l'indirizzo. Sta nel prompt di sistema (`Config.prompt_for`), uguale per tutti i livelli,
  ospiti compresi: è un dato della casa, non di una persona, e così il prefisso resta in cache
  (cambia solo con la configurazione). Frase: la casa è lì, per ciò che dipende dal luogo
  (meteo, orari, negozi, eventi) se chi parla non nomina nessun posto; se nomina un posto di cui
  non si sa dove sia (la casa di qualcuno, un locale) si chiede dov'è. Senza città il prompt è
  quello di prima, parola per parola. Non va in `web_dati_privati` (si toglierebbe dalle
  ricerche). Il valore vero sta in `calliope.locale.yaml`.
- **Le estensioni prima di internet**: con almeno un tool `est_*` il prompt dice che le
  estensioni sono funzioni sue aggiunte dalla famiglia, da usare quando fanno proprio quello
  che si chiede, non `web_cerca` né `biblioteca_cerca`; e la frase del web diventa «chiama
  l'estensione che lo fa, se c'è, altrimenti web_cerca». Detta solo dopo la frase del web, il
  4B non la seguiva (0/2): conta l'ordine e la frase del web stessa. Il prompt cambia solo
  quando un'estensione si attiva o si spegne (cambia già l'elenco dei tool).
- **Misura** (`prove/prova_citta_casa_ollama.py`, gemma4 e4b locale, docker finto, 3
  ripetizioni; tra parentesi il codice di main): con città ed estensione «Che tempo fa?» e «Che
  tempo farà domani?» → l'estensione con la città 6/6 (0/6: chiede la città); senza
  estensione → internet con la città 3/3 (0/3: «meteo oggi», il caso della DGX); «Che tempo
  fa a Parigi?» → Parigi, mai la casa, 6/6 (6/6; con l'estensione la usa 3/3 contro 0/3);
  «Che tempo fa da Ettore?» → chiede dov'è, mai la casa, 3/3 (3/3; con la prima frase, senza
  «un posto di cui non sai dove sia», 0/1: cercava il meteo della casa); notizie di sport con
  la città dentro 1 volta su 7 (si conta). `prova_estensione_nominata_ollama` e
  `prova_web_ollama` invariate (1 giro). Da guardare sulla DGX col 26B.
- **Dopo una ricerca** (unione con `approfondisci-notizie`, `RICERCA_MSG`): nella stessa
  conversazione «Sentimi le notizie di sport» e poi «Che tempo fa?». Senza estensione →
  internet con la città 3/3: `RICERCA_MSG` («se parla d'altro questa riga non conta») non
  disturba. Con l'estensione **0/3, e il 4B inventa il meteo** («sereno, 18 gradi»), con la
  rete `ricerca_recente` accesa o spenta (3/3 e 3/3 uguali): il modello chiama
  l'estensione con la città, ma la politica la ferma. Un'estensione che legge internet è
  un'«azione» (`estensioni/servizio._agisce`: `rete.pubblica` o `host`) e, con un risultato web
  nella conversazione, «Che tempo fa?» non è una richiesta d'azione (`chiesta_azione`) →
  `politica_azione_non_chiesta`, prima volta «rifiuta» con «rispondi con quello che vedi o
  leggi», e il 4B risponde inventando. Non dipende da questo ramo (la città e la frase del prompt
  lo rendono solo più frequente: senza, l'estensione non si chiamava proprio). Da decidere nella
  sicurezza per valore ([sicurezza-politica](sicurezza-politica.md)): un'estensione che solo
  legge internet, senza dati da mandare (`invia` vuoto, niente `scrive` né `legge.dati`), con
  argomenti detti dalla persona o presi dal prompt di sistema (la città) potrebbe valere come
  lettura. In `prova_citta_casa_ollama` il caso è contato, non fa fallire.

## Giro di prova del 09/10 mattina: tetto delle correzioni, cortesia, risposte riservate (09/10, ramo `ricerche-distanza`)

Dal giro vero della DGX (09/10, 11:03–11:24; casi delle ricerche in
[biblioteca](biblioteca.md) e [contesto-conversazione](contesto-conversazione.md)).

- **Il tetto dei giri di correzione non teneva** (`calliope/brain.py`). Alle 11:03 tre
  `web_cerca` fermati e la quarta giusta, con `tool_correzioni_max` = 2. Il difetto: il tetto
  limitava solo i giri con la spinta (testo senza chiamata, `CORREZIONE_NUDGE`); un modello che
  richiamava subito il tool, di nuovo sbagliato, non consumava giri e andava avanti fino a
  `max_tool_turns`. Ora ogni passata dopo un errore correggibile conta; finiti i giri, con
  l'ultimo tool ancora fermo, un'ultima passata senza tool con l'errore davanti
  (`CORREZIONE_ESAURITA`: chiedere il dato o dire che non ci è riuscita, senza inventare),
  regola `correzioni_esaurite`. Prove a secco in `prova_dialogo_tool` (tre richiamate sbagliate:
  niente quarta chiamata; contrari: corretta al secondo giro, `tool_correzioni_max` = 3).
- **Cortesia dopo un'offerta** (`calliope/ciclo.py`, `Ciclo._chiusure`). Alle 11:24, dopo «… se
  vuoi cerco su internet», «Sì, grazie.» è arrivato come «Grazie.» (così nel registro) →
  «Prego, lo metto in conto», nessuna ricerca. Il blocco dopo una domanda valeva solo per la
  forma «conferma» («ok»), non per «grazie», e non vedeva le offerte senza punto
  interrogativo. Ora `Brain.ultima_domanda` vale per la domanda finale e per l'offerta finale
  (`brain.OFFERTA`: «se vuoi», «se ti va», «se preferisce», «dimmi se», «fammi sapere se»,
  «vuoi che…» nell'ultima frase; forma chiusa sulla frase di Calliope che toglie una
  scorciatoia e non decide niente, principio 10), e vale anche per «grazie»: la frase va al
  modello, regola `cortesia_dopo_domanda`. «Sì, grazie.» e «No, grazie.» non sono mai state
  chiusure (vanno al modello; il caso del 07/10 in `prova_corsie` passa). Contrari in
  `prova_testo` (risposte normali, «se» o «vuoi» in una frase non finale) e in `prova_ciclo`
  («Grazie.» dopo una risposta normale resta cortesia).
- **Traccia delle risposte riservate** (`brain.traccia_risposta`, `Ciclo._oscura_registro`):
  con un tool riservato (`conversazione_cerca`, documenti di casa) la risposta resta fuori dal
  registro dei turni; ora c'è `risposta_traccia` = {caratteri, frasi, non_so (dichiara di non
  sapere o non trovare: `NON_SO` o `NON_TROVO`), finisce_con: domanda | offerta | null},
  accanto a `risposta_parole` e ai tool con l'esito. Nessun testo: `prova_ciclo` lo controlla
  sul file scritto da `TurnLog`.

## Il meteo di casa nel prompt (09/10 pomeriggio, ramo `meteo-casa`)

Seguito della sezione sulla città della casa. Decisione di Dario: il meteo senza luogo è quello di
casa; il modello sceglie (principio 10) con un contesto chiaro e la disponibilità vera, passata
da `Brain._system_messages` a `Config.prompt_for` (`meteo_casa`, `citta`, `citta_salva`):

- **entità meteo esposta in HA** (`meteo_leggi` registrato, `allinea_meteo`): «Il meteo senza un
  posto nominato è quello di casa: chiedilo a meteo_leggi…; per un altro posto non usarlo, e se
  chi parla nomina un posto di cui non sai dove sia chiedi dov'è». La frase del web diventa «Per
  il meteo di altri posti, le notizie…», la frase della città non dice più «meteo» (resta per
  orari, negozi, eventi); senza web «Non puoi sapere le notizie né il meteo di altri posti».
- **solo la città** (configurazione valida o salvata a voce, `calliope/luogo.py`): la frase della
  città di prima, parola per parola.
- **niente**, con web o estensioni: «Non sai in che città è la casa dove sei: se una richiesta
  dipende dal luogo… chiedi in che città è la casa; quando te lo dice, chiama citta_casa_salva
  con la città e rispondi alla richiesta per quella città». Senza web né estensioni nessuna
  frase (non servirebbe a niente).
- Il prompt cambia solo quando cambia l'esposizione o si salva la città: il prefisso nuovo si
  scalda (`prefisso_scaldato`). La città salvata vale come configurazione anche per la politica
  (`Turno.da_config`).
- Regole nuove nel registro dei turni: `citta_casa_proposta` (una conferma senza la proposta in
  sospeso vale come proposta), `citta_casa_solo_admin`. Dettagli, casi e misure in
  [casa](casa.md) (stessa data).

## La risposta uguale alla precedente e «ricominciamo» come tool (09/10 sera, ramo `sera-voce-conversazione`)

**Caso vero della DGX** (09/10 19:06:49 e 19:07:04): a «No, mi riferivo esattamente alla richiesta
che ti avevo fatto un attimo fa.» e poi a «Punto prima.» il modello (26B) ha detto due volte,
identica, «Mi hai chiesto esattamente cos'è che mi avevi chiesto un attimo fa. Un loop degno di
un film di Christopher Nolan, ma con meno effetti speciali.»

**Fatto** (rete del modello `risposta_ripetuta`, `calliope/ripetizione.py`): `ClaimHold` trattiene
anche la prima frase che comincia come la risposta precedente (nessuna latenza in più: la voce
aspetta comunque la fine della prima frase) e, se comincia così, il resto; a risposta finita, se
è quasi uguale per intero (almeno 8 parole, somiglianza delle parole 0,85), non si dice né entra
nella storia e il modello riceve `RIPETUTA_NUDGE` (rispondi a quello che ha detto adesso; se non
capisci chiedi; se ti ha chiesto di ripetere, ripeti), una volta: la seconda risposta si dice
anche se uguale. Regola `spinta_ripetuta`. Le risposte brevi uguali («Fatto.», «Va bene, nessun
problema.») non si guardano. Alla stessa domanda (quasi uguale alla precedente) la stessa risposta va bene: la rete non guarda (trovato con `prova_corsie_satelliti`, «Che tempo fa domani?» chiesto di nuovo). Si spegne con `llm_reti_spente`. Col modello locale il caso non si
riproduce (0/3: la e4b risponde in un altro modo), le prove sono a secco
(`prova_conversazioni`: caso vero, ripetere chiesto, breve uguale, risposta diversa, rete spenta).

Il tool `conversazione_nuova` (stesso giorno) e la coda dopo una pausa sono in
[contesto-conversazione](contesto-conversazione.md).

## Chiamate ripetute nella stessa risposta e passata finale (09/10 sera, ramo `sera-politica-strumenti`)

- Una chiamata identica (tool e argomenti normalizzati, `brain.chiave_di_chiamata`) a una già
  fatta nella stessa risposta non si riesegue: il modello riceve l'esito della prima con una
  `nota` (regola `chiamata_ripetuta`; caso vero della DGX delle 20:39: due `casa_comando`
  uguali, la seconda fermata dalla politica e la domanda detta dopo «Ho spento…»). Il rifiuto
  leggero della politica non conta come esito (il modello che insiste porta la domanda alla
  persona). Anche il giro di correzione ne beneficia: una richiamata identica sbagliata riceve
  lo stesso errore senza rieseguire.
- La passata finale senza tool non ha più la spinta dell'ultimo giro (`tail` azzerato: prima
  c'erano insieme «richiamalo» e «non richiamarlo»), e una passata finale vuota dice il
  ripiego (`vuoto_ripiego`). Dall'analisi delle regole § 3.7; dettagli in
  [sicurezza-politica](sicurezza-politica.md).
- I campi della forma degli errori di `tools/dialogo.py` (`campo`, `correggibile`) e l'elenco
  dei lavori veri di `lavoro_risultato` non entrano più nella busta dei dati non fidati
  (`_CAMPI_ERRORE`): un errore senza dati non contamina la conversazione.

## Stato del dialogo, passo 0: i dieci buchi provati, il nome vero, il «no» all'agente (10/10, ramo `stati-passo0`)

Prima di cominciare la macchina a stati ([progetto della macchina a stati](../ricerche/2026-10-10-macchina-stati.md), § 1.10 e § 8) una prova per ciascuno dei
dieci stati che rischiano di non essere gestiti, a secco: `prove/prova_stati_buchi.py`. Tutti e
dieci si riproducono con il codice di main a e023602. Sei restano **documentati** come buchi
«attesi da correggere» con il passo che li chiuderà (la prova fallisce quando un passo li
corregge, e va trasformata in una verifica con i contrari): 1 e 2 al passo 3, 4, 5 e 7 al passo 5,
8 al passo 2. Quattro sono **corretti** subito (3, 6, 9, 10).

- **«Vuoi dirmi il tuo nome?»** dopo la registrazione di Primo/Prima (buco 9). Prima
  `pending_real_name` non scadeva e qualunque frase di al più cinque parole, di chiunque, rinominava
  il profilo: con il codice di prima «Sì.» diventava il nome «Sì» e «Che tempo fa domani?» il nome
  «Che Tempo Fa Domani». Ora l'attesa dura `NOME_VERO_ATTESA_S` (120 s, `calliope/ciclo.py`), vale
  solo per la voce appena registrata (con il riconoscimento acceso) e per una risposta sola; il
  nome vale solo in **forma chiusa intera** (principio 10, `wakeword.risposta_al_nome`): una
  presentazione («Mi chiamo Dario», «Il mio nome è Maria Rosa», «Sono Luca» con il nome maiuscolo)
  o il nome da solo (una parola che non è una risposta comune, due con la seconda maiuscola).
  «Sì» chiede il nome e aspetta ancora, «no» chiude, tutto il resto va al modello (che ha
  `rinomina_interlocutore`) come una frase nella finestra d'ascolto. Regole `nome_vero_si`,
  `nome_vero_no`, `nome_vero_al_modello`, `nome_vero_altra_persona`, `nome_vero_scaduto`
  (`nome_detto` resta). Casi e contrari in `prova_testo` e `prova_stati_buchi`.
- **Il «no» a una domanda dell'agente** (buco 3): la domanda a metà lavoro passava da
  `_rifiuto_proposta` come una proposta sì/no, il «no» finiva tra i rifiuti e la politica bloccava
  `lavoro_rispondi` (`politica_proposta_rifiutata`): l'agente non riceveva la risposta e il lavoro
  aspettava fino alla scadenza (120 minuti). Ora l'offerta della domanda dell'agente ha
  `risposta: True` (`Lavori.offerta_risposta`, salvato da `Brain.set_pending`): un «no» è la
  risposta, la proposta resta e il modello la passa con `lavoro_rispondi`. Regola
  `risposta_non_rifiuto`. Il «no» a una proposta normale («La apro?») resta un rifiuto.

## Stato del dialogo, passo 1: interprete del modello e corsia veloce in ombra (10/10, ramo `stati-passo1`)

Primo passo del piano del progetto [«lo stato del dialogo come macchina a
stati»](../ricerche/2026-10-10-macchina-stati.md) (§ 6), con le due decisioni di Dario del 10/10:
la macchina **non interpreta il linguaggio** (il significato della risposta lo dà il modello in
forma strutturata, o una corsia veloce per le forme chiuse dette per intero) e gli scambi fra
macchina e modello **non inquinano la conversazione**. **In ombra: nessuna decisione di oggi
cambia.**

- **Moduli.** `calliope/stato_dialogo.py`: l'ossatura (`Proposta`, `Chi`, `StatoPersona`,
  `StatoCorsia`) con **adattatori in sola lettura** sugli stati di oggi (`Conversazione.pending`
  con il tool del turno lasciato da `_take_pending`, la domanda della politica, la frase di sfida
  di `SpeakerContext`, lo sviluppo aperto, il cancello 2 dei minori), il blocco dello stato, la
  decisione della macchina con le priorità del § 3.3 (`decidi`) e il consenso del progetto (§ 3.5,
  `consenso_progetto`, solo per il confronto), il confronto per il registro. È una facciata: non
  scrive niente negli stati di oggi. `calliope/risposte.py`: la corsia veloce (`forma_chiusa`).
  `calliope/tools/proposta.py`: lo schema del tool di risposta.
- **`proposta_rispondi(esito, proposta, correzione, quando)`**, esito `si | no | correzione |
  rinvio | altro`: sempre negli schemi, uguale per ogni livello (uno schema in più: il prefisso
  cambia una volta sola). Lo gestisce Brain (`_proposta_rispondi`), mai il registro. In ombra
  `si` diventa **la chiamata che il modello farebbe oggi**: il tool proposto con gli argomenti
  della proposta, attraverso `ToolRegistry.call` e la politica di oggi (decide lei; nella storia
  resta come chiamata del tool vero); `no`, `correzione`, `rinvio`, `altro` non fanno niente
  (oggi, senza un sì, il modello non chiama il tool e la proposta resta: il rifiuto lo decide
  ancora `politica.rifiuto` all'inizio del turno). Il modello che chiama direttamente il tool
  proposto (il sì implicito di oggi) resta il percorso di sempre. Vale solo con una proposta
  sì/no aperta per chi parla, **nella prima passata** e **prima di un dato non fidato letto nella
  stessa risposta**; altrimenti un errore corto e niente (scartata: `nessuna_proposta`,
  `seconda_passata`, `dopo_dato`, `proposta_diversa`, `tipo_dato`, `chiusa`, `esito_non_valido`).
  A turno finito le chiamate a `proposta_rispondi` e i loro esiti escono dalla storia
  (`_togli_proposta_rispondi`, § 3.8 del progetto).
- **Il blocco dello stato** (≤ 520 caratteri, effimero: nei dati del turno subito prima della
  frase, mai nella storia né nel prompt di sistema) prende il posto di `PENDING_MSG` /
  `PENDING_LATER_MSG` per le proposte sì/no: «Stato del dialogo: proposta aperta p3, «…?»
  (casa_comando con comando="…", gravità E1), chiesta nell'ultima risposta. Chi parla l'ha
  ricevuta, voce sicura. Se la frase risponde alla proposta, chiama proposta_rispondi con
  l'esito…». Gli argomenti restano come in `PENDING_MSG`: in ombra la chiamata diretta del tool
  proposto è il percorso di oggi, e alcuni argomenti riconoscono l'offerta (l'id `proposta` di
  `lavoro_affida`: senza, `prova_lavori_riavvio` e `prova_agenti` fallivano, il «sì» diventava una
  richiesta nuova con la sfida). Dal passo 2, quando la macchina eseguirà lei la proposta, si
  potranno togliere. Le domande che chiedono un dato (testo proprio del tool, come la domanda
  dell'agente, o una domanda non sì/no) tengono il loro messaggio di oggi (`set_pending` segna
  `su_misura`).
- **La corsia veloce** (`risposte.forma_chiusa`): ogni pezzo della frase, tolti il nome e i
  riempitivi in testa e in coda, è una forma dell'elenco (`si`: sì, certo, vai, procedi, ok, va
  bene, d'accordo, perché no…; `no`: no, no grazie, annulla, lascia stare, non importa, per ora
  no…; `stop`: basta, stop; `grazie`: grazie, perfetto, ottimo); l'uscita
  (`wakeword.uscita_intera`: la frase intera, senza il ripiego sulla prima clausola) e
  «ricominciamo» per intero, mai con un «sì» nella frase. Tutto il resto va al modello. I casi e
  i contrari (le frasi del § 3.5 dell'analisi del 09/10: «No, mi va bene», «Sì, però fallo dopo»,
  «Si chiama Marco», «Sicuro?», «Sì, puoi andare», «Ok, esci»…) in `prove/prova_testo.py`. In
  ombra non decide niente: si scrive nel confronto.
- **Registro dei turni**: campo `dialogo_ombra` (nessun testo, nessun valore): la proposta (id,
  origine `tool | politica | forse`, tipo `si_no | dato`, gravità, sfida della classe, da quanti
  turni), chi parla (`come`, sicurezza), `forma_chiusa`, `lessico` (come leggono la frase
  `politica.consenso` e `rifiuto`), `modello` (l'esito valido di `proposta_rispondi`), `diretta`,
  `scartate`, `consenso` (del progetto), `macchina`, `via` (corsia, modello, diretta, sfida,
  pavimento), `oggi` (eseguita, sfida, domanda, fermata, rifiutata, resta, sostituita, chiusa),
  `accordo` e `disaccordo` per categoria (`esegue`, `chiede`, `chiude`, `resta`: per esempio
  `chiude_vs_resta`); in più `sfida`, `attivita`, `chiusa_da`, `cancello`, `proposte_risposta`
  (due domande nella stessa risposta), `interrotta`. Le frasi che il ciclo decide **prima** di
  Brain (interruzione, uscite, chiusure, cancello 2) con una proposta aperta hanno il loro
  confronto (`prima_di_brain`, da un'istantanea presa prima della fase: un'uscita chiude la
  conversazione). `calliope stato --turni` ha una sezione «Stato del dialogo»: proposte aperte,
  il modello chiama o non chiama `proposta_rispondi`, chiamate dirette, corsia veloce, scartate,
  accordo e disaccordi per tipo, esiti del modello e consenso del progetto.
- **Interruttore** `dialogo_interprete` in `Config` (sezione `llm`): `ombra` (predefinito),
  `spento` (il percorso di prima, identico: niente schema, niente blocco, niente confronto).
  `acceso` (la macchina che esegue la proposta) non è realizzato: la configurazione lo rifiuta e
  resta `ombra`.
- **Prove**: `prova_stato_dialogo` (a secco: funzioni pure, `si` uguale alla chiamata diretta e
  allo spento con le stesse esecuzioni e regole della politica, gli altri esiti senza effetto,
  difese, storia pulita, due proposte, proposta + sfida, sviluppo, cancello, conversazione chiusa,
  frasi decise prima di Brain, banco nuovo); `prova_testo` (corsia veloce, 60 casi);
  `prova_dialogo_ollama` (il modello vero). `prova_brain`, `prova_conferme` e `prova_agenti` accettano il blocco
  al posto di `PENDING_MSG`.
- **Misura col 4B (gemma4 e4b sul portatile, 10/10, `prova_dialogo_ollama 2`, blocco con gli
  argomenti)**: 100 risposte a una proposta aperta (16 frasi del registro e dell'analisi, più una
  correzione, su tre proposte: «La apro?» di un tool, «Vuoi che accenda la luce della taverna?»,
  la domanda della politica per registrare una voce). Il modello chiama `proposta_rispondi`
  **46 volte su 100**, chiama direttamente il tool proposto 15, nessuno dei due 39 (tutti i «no»,
  che il 4B dice solo a parole: la proposta resta, come oggi; e qualche sì perso, «Sì, grazie»
  alla registrazione). Esito giusto 42/46: i sì chiamati 31/31, i rinvii 11/12 («Sì, però fallo
  dopo», «Magari stasera»); «altro» chiamato 4 volte, sempre come `si` (sbagliato: «Sì, però
  ascolta, stiamo uscendo a cena» dopo «La apro?»); correzioni mai. Per proposta: la domanda
  della politica 21/32, «La apro?» 17/34, la luce 8/34 (il 4B chiama `casa_comando` da solo, 12).
  Con la corsia veloce un esito strutturato c'è per 73/100. **Accordo con lo spento** (stessa
  esecuzione per la stessa frase): 92/100; degli 8 diversi, 5 sono rinvii che oggi eseguono
  subito e in ombra no (la macchina ha ragione), 1 «Sì, però ascolta…» che il modello in ombra
  chiama `si` (a conversazione pulita la politica di oggi non giudica il consenso di un E1), 1
  «No, mi va bene» e 1 «Sì, grazie» eseguiti solo nello spento. «No» eseguiti: 0 in tutti e due
  i modi. **Latenza**: lettura del prompt 0,07 s in tutti e due i modi; prima frase mediana +0,07,
  +0,10, +0,13 s in tre misure (0,49–0,62 s: piccola, da rimisurare col 26B); stato del turno e
  corsia veloce 0,03 ms; niente secondo modello. Il blocco con «e non {tool}» non cambiava niente
  (38 %); la descrizione «chiama questo al posto del tool proposto» porta al 40–46 %. **Il 26B
  va misurato sulla DGX** (sotto).
- **Cosa guardare sulla DGX per decidere il passo 2** (`calliope stato --turni`, sezione «Stato
  del dialogo»): quante proposte sì/no il 26B risponde con `proposta_rispondi` (e quante con il
  tool diretto o senza niente); i disaccordi per tipo: `chiede_vs_esegue` (il consenso del
  progetto avrebbe chiesto la sfida dove oggi `conferma_breve` esegue: l'attrito in più
  dell'accensione, «Rischi» del progetto), `esegue_vs_chiede` (oggi si chiede e il progetto
  eseguirebbe: attrito in meno), `chiude_vs_resta` (rinvii e «no» che oggi lasciano viva la
  proposta), le frasi `prima_di_brain` (uscite e stop con una proposta aperta: i casi del § 3.6
  dell'analisi); le `scartate` per `dopo_dato` e `seconda_passata` (poche, e mai seguite da
  un'esecuzione). E la prima frase dei turni con una proposta, con e senza (`dialogo_interprete:
  spento` nel locale per un giorno di confronto). Per tornare indietro: `dialogo_interprete:
  spento` in `calliope.locale.yaml`.
- **Il giro col 26B del 10/10 mattina** (ramo `stati-indagine-26b`, § 9 del
  [progetto](../ricerche/2026-10-10-macchina-stati.md)): su 9 risposte a una proposta il 26B
  chiamava `proposta_rispondi` **6 volte** (su 7 risposte vere; le 2 frasi che parlano d'altro
  senza tool, giusto), non 1: 5 chiamate erano scartate per `proposta_diversa` e il riassunto le
  contava come «non chiama». Causa: le proposte di `sviluppo_apri` e `lavoro_affida` hanno un
  argomento che si chiama anch'esso `proposta` (l'id del lavoro, «L1»), che il blocco mostra e la
  riga della fase dello sviluppo dice di usare; il modello passava `proposta="L1"`. Scartata, la
  chiamata non diventava quella di oggi e il modello dichiarava un'azione mai fatta («procedo con
  lo sviluppo» senza tool, «Non ci sono riuscita»): col 4B sui turni rigiocati `sviluppo_apri` al
  «sì» 1/5 e 0/5 in ombra contro 3/5 e 5/5 con lo spento. **Corretto** (in ombra):
  `stato_dialogo.id_della_proposta` accetta l'id vuoto, il suo, un valore dei suoi argomenti o il
  nome del tool; un altro id del dialogo resta scartato; `dialogo_ombra.id_argomento`; il
  riassunto conta a parte le chiamate scartate. Dopo: 5/5 e 5/5, valide 20/25 contro 11/25. Restano
  fuori dall'ombra e annotati nel § 9: «Chiudo lo sviluppo…?» che non diventa mai una proposta (la
  domanda non è in fondo alla risposta; *corretto il 10/10, ramo `sviluppo-chiusura`*) e il
  secondo giro del modello per `no`, `rinvio`, `altro`
  (~+1 s col 26B).

## Le fasi dello sviluppo nelle dichiarazioni d'azione (10/10, ramo `giro-ombra-correzioni`)

Giro vero della DGX del 10/10 mattina, satellite «studio», modalità sviluppo aperta:
- 06:10:40 «Annullahi.» (Whisper per «Annulla») → «Ho capito, l'analisi è stata annullata.
  Siamo ancora in fase di analisi…», nessun tool, e lo sviluppo restava aperto;
- 06:12:47 «Non c'è problema.» → la rete scatta sulla prima passata (`spinta_dichiarata`), e
  dopo la spinta il modello dice «D'accordo, procedo allora con lo sviluppo. Siamo passati alla
  fase di sviluppo…», di nuovo senza tool; il turno dopo «Restiamo pure in fase di analisi».

**Due cause diverse.** Alle 06:12:47 la causa a monte è l'ombra del passo 1 (voce qui sopra, ramo
`stati-indagine-26b`): il 26B rispondeva al «sì» con `proposta_rispondi(proposta="L1")`, la
chiamata era scartata (`proposta_diversa` nel `dialogo_ombra` del turno) e il modello, senza la
chiamata di oggi, dichiarava il passaggio. Corretta lì (`id_della_proposta`). Alle 06:10:40 invece
nessuna `proposta_rispondi` (nel `dialogo_ombra` `modello: null`): è una dichiarazione senza tool
e basta, il caso della rete. La correzione qui sotto vale per entrambe le forme: una frase così,
da qualunque strada arrivi, non si dice senza il tool.

**Perché la rete non scattava** (nessuna esclusione per la modalità sviluppo): il vocabolario di
`ACTION_CLAIM`. Il passivo vale solo con una cosa di Calliope come soggetto (`_CLAIM_THINGS`), e
analisi, sviluppo, collaudo, revisione, fase e modalità non c'erano; «procedo … con» ammetteva tra
i due solo «subito/ora/adesso/quindi», non «allora»; un cambio di fase («siamo passati alla fase
di…», «passiamo allo sviluppo») non era una forma della rete. Dopo la spinta il controllo è solo
sulla prima frase (`ClaimHold`), e la seconda passata passava intera.

**Correzione** (generale, non per le due frasi): `_CLAIM_THINGS_PASSIVE` aggiunge al passivo le
fasi e la modalità («l'analisi è stata annullata», «lo sviluppo è stato sospeso», «la revisione è
stata chiusa»; non alla forma senza verbo, dove «il collaudo dei file creati…» descriverebbe);
«procedo» ammette fino a due avverbi di raccordo (allora, dunque, quindi, pure, senz'altro,
intanto…); il cambio di fase è una dichiarazione, al passato («siamo/sono/è passat-, tornat-,
entrat- alla/allo/in [fase di] sviluppo, analisi, collaudo, revisione, attivazione, modalità») e
al presente («passiamo/torniamo/entriamo allo sviluppo»). Contrari in `prova_giro_ombra.py`: lo
stato («siamo all'analisi», «siamo ancora in fase di analisi», «restiamo pure in fase di
analisi», «lo sviluppo resta aperto»), l'offerta («quando vuoi[,] passiamo allo sviluppo», «se
vuoi, torniamo all'analisi», «dopo passiamo al collaudo»), le domande, la negazione, «procedo con
la ricerca». Come le altre forme, solo nelle risposte senza tool del turno: un passaggio di fase
fatto davvero da `sviluppo_passo` si dice. Con Brain e un modello finto le due frasi del giro non
si dicono (la prima diventa la chiamata del tool dopo la spinta, la seconda «Non ci sono
riuscita…», `dichiarata_taciuta`).

## Azioni al presente su una cosa di Calliope, e la storia uguale a ciò che si è sentito (10/10, ramo `sviluppo-chiusura`)

Secondo giro vero della DGX del 10/10 (07:11–07:21, satellite «studio»; la chiusura dello
sviluppo e i titoli in [agenti-estensioni](agenti-estensioni.md)).

**Dichiarazioni al presente.** 07:14:12 «No, chiudilo.» → «Ho capito, chiudo definitivamente lo
sviluppo di «…».», nessun tool, e lo sviluppo restava sospeso. `ACTION_CLAIM` prendeva il
presente solo a inizio risposta e solo per i verbi della casa e dei file. Ora (generale) un verbo
al presente sulle cose di Calliope (chiudo, apro, riapro, sospendo, fermo, annullo, riprendo,
interrompo, blocco), al più due avverbi (definitivamente, subito, allora, proprio…) e l'oggetto
(sviluppo, lavoro, programma, estensione, anche al plurale). Contrari (`prova_giro_chiusura`): le
domande («Chiudo lo sviluppo?», «Lo chiudo?»), le offerte («se vuoi[,] chiudo lo sviluppo»,
«quando vuoi apro il programma»), un condizionale nella stessa proposizione («chiudo lo sviluppo
se me lo confermi», «…quando vuoi»: vale ora anche per la forma a inizio risposta, «Accendo la
luce quando vuoi»), «non chiudo», «chiuderei», «posso chiudere». Limite: «Chiudo lo sviluppo, se
vuoi.» (condizionale dopo la virgola) resta una dichiarazione, come «Apro il file, se ti serve
altro dimmelo.». Come le altre forme vale solo nelle risposte senza un tool d'azione riuscito: la
frase pronta di `sviluppo_passo` («D'accordo: chiudo lo sviluppo…») si dice.

**La storia è ciò che la persona ha sentito.** Dario alle 07:17:50: «questa cosa della frase che
dici è qualcosa che non arriva dall'LLM e non è nel contesto». Verificato col turno ricostruito
(07:17:03–07:18:33, ciclo della voce con la resa per la voce di `Ciclo._frase_da_dire` e Brain
vero con un modello finto): la frase pronta di `sviluppo_passo` («Chiudo lo sviluppo…?») **c'era**
nella storia, uguale parola per parola a ciò che è andato alla voce (`risposta` del registro), dopo
la chiamata e il risultato del tool; così la riga in coda dello sviluppo (`_aggiungi_detto`) e gli
annunci (`record_announcement`). Il giro a vuoto veniva dalla proposta non registrata (sopra e in
agenti-estensioni): senza `PENDING_MSG` il modello non sapeva come confermare (lo dice lui alle
07:17:50). Dove invece la storia poteva divergere da ciò che si è sentito: la resa per la voce
(markdown tolto, nomi dei tool detti a parole, una frase che annuncia un tool taciuta, «secondo
Wikipedia» tolto) e una frase cambiata dai controlli dell'uscita senza fermate (la fonte aggiunta).
Ora, a turno finito e non interrotto, `Ciclo._storia_come_detta` → `Brain.allinea_detto`: ogni
messaggio dell'assistente del turno diventa la sua resa per la voce; se insieme non danno le frasi
andate alla voce, il testo dei messaggi con le chiamate si svuota e l'ultima risposta diventa ciò
che si è sentito. Regola `storia_come_detta` quando la storia cambia (di solito non cambia: la
maggior parte dei turni è testo semplice o frasi pronte). Restano come prima: l'interruzione
(`record_interruption`, solo le frasi sentite per intero), le risposte fermate dal guardiano e dai
controlli dell'uscita (`correggi_storia`), gli scambi tecnici (chiamate e risultati dei tool: la
loro pulizia è il passo della storia pulita, § 3.8 della [macchina a
stati](../ricerche/2026-10-10-macchina-stati.md)). **Fuori dalla storia restano le frasi
d'attesa** («Vediamo…», «Controllo nella biblioteca.»), come dal 26/09: non dicono niente della
conversazione e, viste come risposte di Calliope prima di un tool, il modello tenderebbe a
ripeterle; da decidere con Dario se vanno dentro. Streaming: niente cambia durante la risposta, la
storia si tocca dopo l'ultima frase. Cache del prefisso: cambia solo il turno appena finito, che
il turno dopo rilegge comunque dalla frase nuova; nei turni che non cambiano nulla, niente.

## Forme chiuse storpiate da Whisper (10/10, ramo `forme-storpiate`)

**Casi veri della DGX** (whisper.cpp, satellite «studio», giri delle 06:09–06:18 e 07:11–07:21,
modalità sviluppo aperta): le forme chiuse brevi arrivano storpiate e le storpiature facevano
partire azioni vere.
- «Calliope ricominciava.» (07:18:55) → `sviluppo_passo(riprendi)`: ha RIPRESO uno sviluppo
  sospeso invece della conversazione nuova; «Calliope ricominciavo.» (07:11:47) è finito in
  `conversazione_nuova` per caso;
- «E lì appena ricominciamo.» (07:16:39, era «Calliope, ricominciamo») →
  `sviluppo_passo(avanti)`: ha FATTO PARTIRE il lavoro dell'agente; «Da lì poi ricominciamo.»
  (06:13:43) e «E lì è per ricominciare.» (09/10 21:03) lo stesso, senza danni;
- «Am nulla il lavoro.» (07:12:53) → `sviluppo_passo(rifai)`: ha RIFATTO il lavoro invece di
  annullarlo; «Annullahi.» (06:10:40), «Nulla è lavoro.» (06:13:05), «Anzi, no a nulla.» (02/10);
- «Spendilo.» (07:14:44) → `avanti`, «Spendilo pure.» (07:21:06) non capito; «Chiudin.»,
  «Giudino.», «Chiudino sviluppo.» per «chiudi/chiudilo»; «Alla ora, ok.» (06:18:17, era
  «Calliope, ok») → l'ora.

**Tre pezzi**, dal più stretto al più largo (principio 10: la trascrizione è ciò che il modello non
vede; sempre la frase intera, mai una parola dentro una frase):

1. **«Ricominciamo» storpiato è la forma chiusa** (`wakeword.nuova_conversazione_come`, regola
   `nuova_conversazione_storpiata` accanto a `nuova_conversazione`), come il nome e «esci»: un'altra
   forma del verbo detta da sola (`ricominci` + a, o, amo, ammo, ava, avo, avamo, ano, are, ato…),
   «ri cominciamo», una parola che comincia con «ri» e somiglia a «ricominciamo» ≥ 0,88
   («riccominciamo», «ricominchiamo»; non «riconosciamo», «ricomponiamo» a 0,83); e il **nome
   storpiato in più parole davanti** (`wakeword.prefisso_nome`): la somiglianza delle lettere non
   li distingue («dalipoi» 0,53 contro «allora» 0,57), lo scheletro delle consonanti di «Calliope»
   sì: c-l-p con la prima che cade o diventa un'altra occlusiva e una nasale o una r in coda («e lì
   appena» → l-p-n, «da lì poi» → d-l-p, «e lì è per» → l-p-r), da una a tre parole e al più 10
   lettere, una parola sola anche vicina al nome (≥ 0,6: «Luipe» sì, «colpa», «lupo» no); «alla ora»
   è il caso vero senza la p. Solo a voce (uno scritto non è storpiato). L'effetto è reversibile:
   la conversazione resta nell'archivio. Limite noto: «Lì poi ricominciamo.» detto davvero diventa
   una conversazione nuova.
2. **Le altre storpiature sono un dato del turno** (`calliope/storpiature.py` → `suggerisci`,
   regola `forma_storpiata`, campo `forma_storpiata` nel registro dei turni con la forma, mai il
   testo): «La frase è una trascrizione automatica e forse è storpiata: «Spendilo» potrebbe essere
   «sospendilo». Se così ha senso, intendila così; se non è chiaro cosa vuole, chiedilo prima di fare
   qualcosa.», dentro i dati del turno dopo chi parla (come le parole incerte), una risposta sola,
   solo a voce. Forme: «annulla» (annullahi/annullai/annulle…, «am/an/a nulla», «nulla è/il
   lavoro», con il lavoro, lo sviluppo, il programma, tutto), «chiudilo» (chiudin, chiudino,
   giudino, giudilo…; non le forme vere né «giudice», «giudizio»), «sospendilo» (spendilo, spendila,
   spendi, con lo sviluppo; non «spendi tutto»), e il nome storpiato davanti a una forma chiusa
   («Alla ora, ok», «Luipe. Stop.» → «Calliope, ok/stop»). Al più 4 parole, tolti il nome, «anzi»,
   «no», «niente» e i riempitivi in testa. Non decide niente: «Spendilo» è anche una parola vera.
   Nella **corsia veloce** (`risposte.forma_chiusa`, in ombra) solo «annulla» senza oggetto vale
   «no» (a una proposta: la chiude, si richiede).
3. **La rete generale della politica** (`politica.avvio_non_chiesto`, regola
   `politica_avvio_non_chiesto`): `sviluppo_passo` con azione avanti, rifai o riprendi e
   `lavoro_affida` (un lavoro dell'agente che parte o riparte) da una frase **breve** (al più 6
   parole, il nome escluso) che non ha **le parole dell'azione scelta** (`VERBI_AZIONE`, le stesse
   che la politica per valore usa come ancora), né un consenso o la sfida superata, né per avanti e
   riprendi le parole generiche di un avvio (vai, parti, inizia, cominciamo, procedi, passiamo,
   riprendi, continua, approva, attiva…) diventano «Non sono sicura di aver capito: vuoi che
   {cosa}?» (conferma: il «sì» la esegue, `Decisione.accettata`). Alla proposta di questo stesso
   tool la risposta la legge il modello («Non c'è problema.», «no, lascia stare»: `prova_stato_dialogo`
   e `prova_conferma_unica`), salvo una forma storpiata nota («Spendilo.» a «vuoi che vada
   avanti?»). Valutati e scartati: le probabilità per parola di Whisper (un segnale sui nomi, non
   sulle frasi: [parole incerte](../ricerche/2026-10-08-parole-incerte.md); e su whisper.cpp
   costano una richiesta in più) e F0/F1 di `argomenti_incerti` (guardano gli argomenti che
   nominano qualcosa, e qui l'argomento è un'azione scelta in un enum). La rete vale per ogni
   frase breve, non solo per le storpiature: «Szi, vogliati várla!» (08/10) era lo stesso caso.

**Misure** (tutti i turni veri raccolti sul portatile, registri della DGX e del portatile dal 24/09
al 10/10, prove end-to-end comprese: 1531 turni, 1299 frasi distinte):
- «ricominciamo»: 17 esatte di prima, **5 storpiate prese** (i cinque casi veri), **0 falsi**;
- dato del turno: **12 frasi** (i casi veri sopra più «No, niente a nulla.», «Luipe. Stop.»),
  **0 falsi** sulle altre 1287; corsia veloce «no»: 3 («Annullahi.», «Anzi, no a nulla.»,
  «No, niente a nulla.»);
- rete della politica: sui **30 avvii veri** dell'agente (`sviluppo_passo` avanti/rifai/riprendi
  e `lavoro_affida`, 08–10/10) chiede **7 volte**: 6 giuste («Am nulla il lavoro.», «E lì appena
  ricominciamo.», «Spendilo.», «Calliope ricominciava.», «Szi, vogliati várla!», «Rifallo così
  com'è.» che il modello aveva letto come avanti) e 1 dubbia («E lo sviluppo di metricità.» →
  riprendi); le altre 23 eseguono come prima (frasi con le parole dell'azione, consensi, frasi
  lunghe come «Direi che ci siamo, secondo me è a posto.»). Senza le parole generiche di un avvio
  «Riprendiamo lo sviluppo.» (→ avanti) chiedeva anche lui.
- Contrari scritti in `prove/prova_storpiature.py` (150 verifiche: «Ricomincia da capo il
  programma», «Ricominciava a piovere», «Domani ricominciamo», «Annulla la sveglia delle 7»,
  «Chiudi la finestra», «Spendi meno», «Spendi tutto», «Non serve a nulla», «Vai avanti»,
  «Riprova», «Fai una ricerca…»); `prova_ciclo` con «E lì appena ricominciamo.» e «Spendilo.» nel
  ciclo vero.
- **Col 4B** (gemma4 e4b sul portatile, sviluppo al collaudo con il lavoro dell'agente fermato,
  6 frasi × 2 giri, con e senza il dato del turno): nessun lavoro ripartito in nessuno dei 24
  turni. Senza il dato «Spendilo.» e «Giudino.» ricevono «Non ho capito cosa intendi…» (4/4),
  «Annullahi.» `lavoro_annulla` (2/2); con il dato «Spendilo.» e «Annullahi.» sospendono lo
  sviluppo (4/4, «L'agente non sta lavorando: ho sospeso lo sviluppo»), «Giudino.» 1 domanda e 1
  «Chiudilo.» detto come testo (sbagliato, innocuo), «Chiudin.» chiede la conferma di chiudere
  con e senza (4/4). Il 26B va guardato sulla DGX (`forma_storpiata` e
  `politica_avvio_non_chiesto` nel campo `regole`).

## Una voce sola, passi 0 e 1: il registro degli eventi in ombra (10/10, ramo `eventi-passi-0-1`)

Decisione [0027](../decisioni/0027-conversazione-come-registro-di-eventi.md), progetto
[`2026-10-10-registro-eventi.md`](../ricerche/2026-10-10-registro-eventi.md) § 8, passi 0 e 1.
**Niente cambia in ciò che Calliope dice o in ciò che il modello vede**: la storia di Brain resta la
fonte; gli eventi si scrivono accanto e si confrontano. Interruttore `eventi: spento | ombra` (sezione
`conversazioni` di calliope.yaml, predefinito `ombra`; «attivo» è il passo 3, rifiutato e riportato a
`ombra` come `dialogo_interprete: acceso`). Con `spento` niente osservatore, niente campi nuovi,
niente tabella: come prima.

**Che cosa è andato alla voce.** *Storico: dal passo 2 lo dice l'uscita unica (sezione «Una voce
sola, passo 2»), e `Speaker.osservatore` non c'è più.* `tts.Speaker.osservatore` (una funzione, None di solito): `say` e
`say_cached` le dicono ogni frase mandata, `start_turn` le frasi sentite per intero (`played`) e
l'interruzione del pezzo che si chiude. In memoria, dal thread di chi chiama: ~1 µs per frase
(misura della prova), nessun file aperto. Chi ha parlato (l'**atto**) si ricava, nel passo 1, dalla
funzione del ciclo che ha chiamato la voce (`eventi/ombra.ATTI`): `_di_frase` e la ricerca promessa
sono il contenuto della risposta; cortesia, protezione del cancello 2, annunci (documenti,
installazioni, lavori, estensioni), richieste ai tutori, cassetto e moduli sono atti che oggi
**entrano** nella storia; agenda, avvisi ai tutori, registrazione della voce, «Sì?» e «Ciao Ginevra.»,
«chi parla?», «cosa vuoi sapere?», fuori orario e protezione ripetuta, errori sono atti che oggi
**non** ci entrano; frasi d'attesa (`say_cached`, tranne la cortesia), saluto dell'avvio, giochi e
chiusure («A presto!») sono **voluti** fuori. Nel passo 2 l'atto lo dirà l'uscita unica.

**Passo 0: la misura di oggi** (`eventi/misura.py`, campo `parlato` del registro dei turni). A turno
finito, dalle frasi dette, da `played` e dall'ultimo turno della storia di Brain:
- `diverso` (1 se la storia non dice ciò che si è sentito) con i **motivi** del § 1.1: `filtri_frase`
  (resa per la voce diversa dalla storia), `claim_at` (dichiarazione detta e tolta: con le spinte
  `spinta_dichiarata`/`spinta_rinuncia`), `stop_non_detto` («Va bene, mi fermo. (argomento
  chiuso)» scritto da `record_stop` e mai detto), `interrotta_persa` (la frase a metà sentita e
  persa), `interrotta` (la storia ha di più dopo un'interruzione), `capito` (la frase della persona
  riscritta con `⟦capito⟧` accettata), `canale_scritto` (risposta scritta o muta: la storia non lo
  sa), `non_in_storia:<atto>`, `storia_non_detta`; più `voluti` per atto, contati a parte;
- `domande_non_registrate` (frasi sentite che finiscono con «?» senza una proposta aperta in quel
  turno; le frasi si dividono anche dentro un pezzo detto insieme) con i motivi del § 1.2:
  `testo_dopo_la_domanda` (un tool ha proposto, `Brain._offer`, ma la domanda non è in fondo),
  `senza_in_sospeso`, `stato_a_parte` (cancello 1 dei minori), `fuori_dalla_storia`,
  `annuncio_senza_proposta`, `ripeti`, `intendevi`; `domande_registrate` e `offerte` (il modello che
  chiede senza un tool) a parte.
Gli annunci fra un turno e l'altro (timer, documento pronto) non hanno una riga sua: si sommano al
turno dopo della stessa corsia, con `fra_turni: 1`. In `calliope stato --turni` la sezione «Una voce
sola» con gli ATTENZIONE se non sono zero, come la latenza: oggi **non** lo sono per costruzione (è
la base da misurare per una settimana sulla DGX: § 8 del progetto, passo 0).

**Passo 1: il registro in ombra** (`calliope/eventi/`). A turno finito, in cima al giro dopo
(`Ciclo._scrivi_turno`, prima di `TurnLog.write`; la voce ha già finito), gli eventi del turno nel
registro della conversazione (`persona:<id>`, o `ospite:<corsia>` per ospiti e voci incerte): un
segmento per ogni `Conversazione` di Brain, `detto_persona` (con ingressi, trascrizione capita,
modulo, turno escluso), chiamate ed esiti dei tool ricopiati dalla storia di fine risposta,
`detto_calliope` frase per frase con autore e atto, `voce_fine`, proposte aperte e chiuse (dal
`pending` della conversazione), sfida (senza parole), compressione, `turno_chiuso`. Poi la
proiezione del contesto (`proiezioni.turni`, `proiezioni.messaggi`) e il confronto con
`brain.history`, turno per turno: le **differenze nuove** per meccanismo nel campo `eventi_ombra`
(con `contesto_ms`, `byte`, `eventi`, `aperte`, `non_osservati`, `fughe`, `porte`, `troncati`).
Ogni differenza si conta una volta. Le frasi d'attesa restano fuori dal contesto (decisione di
Dario del 10/10, § 4.2).

**«Dimentica le nostre conversazioni»** (§ 2.4, vera dal 10/10). Il tool, al «sì», cancella come
prima l'archivio della persona, ora con `secure_delete`, l'indice FTS5 ricompattato, la
conversazione salvata (`correnti`), i turni orfani e il registro degli eventi (con il checkpoint del
WAL). E, **solo con il registro acceso**, il ciclo a risposta finita chiude e svuota anche la
conversazione in corso senza archiviarla (`Ciclo._conversazioni_dimenticate`,
`Brain.dimentica_conversazione`): è l'unico cambiamento che si sente, voluto dal § 2.4 (prima la
frase restava al modello, in `correnti` e, alla chiusura, tornava nell'archivio e nel riassunto).
Con `eventi: spento` la conversazione in corso resta come prima.

**Come aggiungere un tipo di evento** (ricetta del § 10 del progetto):
1. il tipo, i suoi campi e la visibilità predefinita in `calliope/eventi/tipi.py` (`TIPI`), e se
   serve la sua regola per il disco in `per_disco`;
2. la riga in `PROIEZIONE_CONTESTO` (come si rende, o `ESCLUSO` e perché) e in `PROIEZIONE_TURNI`
   (`calliope/eventi/proiezioni.py`);
3. chi lo scrive: un solo punto, attraverso il registro (`Registro.aggiungi`, mai una lista a mano);
   da un altro registro solo con una porta `porta_*`;
4. una prova nella famiglia `prova_eventi*` e la riga in `prove/elenco.md`.

**Limiti dell'ombra** (scritti anche nel § 8 del progetto): chiamate, esiti e buste si ricopiano
dalla storia (il confronto ne controlla solo la forma nei turni dopo); la posizione delle chiamate
rispetto alle frasi non si sa (la proiezione mette le chiamate prima del testo, il confronto è per
turno); `passata_modello`, `dati_del_turno` e `scheda_mandata` non si scrivono ancora; il pezzo
sentito di una frase interrotta non lo dice il satellite (`interrotta_persa`).

Prove: `prova_eventi` (tipi, proiezioni pure, partizione, porte, due corsie, riassegnazione),
`prova_eventi_ciclo` (passo 0 e ombra su un giro sintetico del ciclo vero, latenza),
`prova_eventi_disco` (riavvio, «dimentica»). Misure: prima frase invariata: con Calliope vera in `prova_satellite` (modello e Whisper finti, Piper vero; 3 giri per lato, 27 risposte ciascuno) `prima_frase_s` mediana 0,09 s prima e dopo (media 0,095 → 0,093 s), prima voce sentita mediana 0,37 s uguale, «dalla fine della frase alla prima voce» 0,63–0,77 s prima e 0,68–0,73 s dopo (rumore della macchina); osservatore della voce ~1 µs per frase; `contesto_ms` al più 0,14 ms (24 turni veri della prova) e 0,06 ms sul giro sintetico; su disco ~0,4–0,6 kB per turno di mediana, fino a ~2,5 kB con risultati di tool.

## Una conferma senza parole, e «ricominciamo» muto sul satellite (10/10, ramo `giro3-correzioni`)

Terzo giro vero della DGX del 10/10 (10:37–10:44, satellite «studio»; l'altro compito
nell'analisi, i titoli e «chiudi tutti gli sviluppi» in [agenti-estensioni](agenti-estensioni.md)).

**«CQD» non è un sì.** 10:39:07, a «…Lo chiudo?» per lo sviluppo delle parole, Whisper ha scritto
«CQD» (forse «Sì, chiudi»): il modello ha richiamato chiudi, la conferma breve l'ha fatto passare
(`conferma_breve`) e lo sviluppo si è chiuso. Ora (`politica.consenso_irriconoscibile`, chiamata
da `ToolRegistry.call` **prima** della conferma breve) la chiamata del tool proposto da una frase
**detta** senza nessuna parola riconoscibile non esegue: «Non ho capito: lo chiudo?», con la
stessa proposta in sospeso (regola `consenso_irriconoscibile`). Vale per ogni strada del «sì»: la
chiamata diretta, la conferma breve, `proposta_rispondi(si)` in ombra (che diventa la stessa
chiamata); la corsia veloce già non prende «CQD» (non è una forma). Non vale per lo scritto (non è
una trascrizione), per la frase di sfida superata, per una proposta che chiede un dato (la domanda
dell'agente) né per gli altri tool. **Riconoscibile** (`risposte.senza_parole`,
`parola_riconoscibile`), senza un dizionario nuovo: le parole brevi chiuse dell'italiano (sì, no,
ok, va, e, il, per, non…), un numero, o una parola di almeno tre lettere con una vocale e una
vocale in fondo, non una sigla tutta maiuscola; il nome non conta; una storpiatura nota
(`storpiature.suggerisci`: «Chiudin», «Spendilo», «Annullahi») ha il suo percorso e non è toccata.
Principio 10: riguarda la trascrizione, che il modello non vede come tale, e l'effetto è una
domanda in più. Per la domanda la politica sa ora la domanda e la cosa della proposta
(`Turno.domanda_sospeso`, `cosa_sospeso`, `risposta_dato`). Contrari in `prova_giro3`: «sì», «sì
sì», «ok», «va bene», «certo», «chiudilo», «d'accordo», «3», le storpiature. **Limite**: una
risposta di una sola parola che finisce in consonante e non è tra le brevi («Sport») vale come
senza parole; a una domanda sì/no non capita.

**«Ricominciamo» muto sul satellite.** Nei tre giri del 10/10 «Calliope, ricominciamo» chiudeva
la conversazione ma Dario non sentiva «Va bene, ricominciamo da capo.» e il ciclo tornava subito
«In ascolto…»; «A presto!» di «esci» si è sempre sentito. Le due strade differivano nell'ordine:
«esci» (`_addormentati`) dice la frase e poi chiude la conversazione, «ricominciamo» chiudeva e
poi diceva. **Non riprodotto in locale** (*storico: la causa l'ha trovata il controllo qui sotto
nel quarto giro, ed era un'altra; vedi la voce del ramo `giro4-correzioni`*): con Calliope vera (Piper, Brain, archivio, corsie, un
satellite finto a livello di protocollo e uno vero in processo con microfono e casse finti, come
`prova_satellite` e `prova_corsie_satelliti`), con la voce riconosciuta e anche detto come
barge-in durante una risposta, la frase arriva e si sente (0,6–0,7 s dalla fine della frase).
Correzione nel solo ramo di «ricominciamo»: la frase prima di `end_conversation("nuova")`, come
«esci»; un'interruzione rimasta accesa (che farebbe scartare la frase senza sintetizzarla) si
azzera; e `Ciclo._di_e_aspetta` controlla, con l'uscita di un satellite, che lui l'abbia detta per
intero (le frasi dette tornano con la fine del turno): se no scrive nel log «[VOCE] il satellite
non ha detto …» con il turno e lo stato della voce, e la regola `voce_frase_non_detta`. **Da
guardare sulla DGX** dopo l'aggiornamento: se la frase ancora non si sente, quella riga del
journal dice dove si perde. Prova: `prova_giro3` (corsia di un satellite finto con lo Speaker
vero: la frase va prima della chiusura, anche con un'interruzione accesa; contrario: il satellite
che non la dice → la regola; «esci» com'era).

## Frasi fuori turno sul satellite, e «…» nel journal (10/10, ramo `giro4-correzioni`)

Quarto giro vero della DGX del 10/10 (11:46–11:51, satellite «studio»; il cambio di sviluppo e
l'elenco degli sviluppi in [agenti-estensioni](agenti-estensioni.md)).

**«Ricominciamo» muto: la causa.** Il controllo messo nel terzo giro l'ha detta al primo turno:
«[VOCE] il satellite non ha detto «Va bene, ricominciamo da capo.» (turno 0, interrotta False,
attesa finita True)». Il satellite scarta le frasi di un turno che non supera l'ultimo fermato
(`client.Riproduttore._scartata`: `turno <= scarta_fino`, che parte da 0 e sale con un «ferma»,
anche suo quando sente il nome). La voce di una corsia nuova (ogni satellite dopo un riavvio di
Calliope, cioè dopo ogni `calliope aggiorna`) sta al turno 0, e il turno sale solo con
`start_turn`, che il ciclo chiamava all'inizio di una risposta del modello e alla sua fine. Una
frase detta fuori da una risposta **prima di ogni altra** partiva al turno 0 e il satellite la
buttava: nei giri del 10/10 «Calliope, ricominciamo» era sempre la prima frase dopo
l'aggiornamento. A metà giro (11:50:48) si è sentita: il turno era già salito. «A presto!» di
«esci» si sentiva solo perché non era mai detto per primo. In locale non si riproduceva perché
le prove facevano prima un turno normale e il satellite finto non controllava il turno.
- **Correzione**: `Ciclo._di_e_aspetta` apre sempre un turno della voce prima della frase
  («ricominciamo», «esci» con `_addormentati`, «Mi spengo. A presto!»), e anche
  `Ciclo._ascolta` lo apre per la frase presa: tutto ciò che si dice prima della risposta del
  modello (uscite, cortesia, registrazione della voce, «Sì?», la frase d'attesa di Whisper su
  CPU, la guardia dei minori) sta in un turno nuovo, che il satellite non ha fermato. Lo aprono
  anche gli annunci fra un turno e l'altro (`_di_gli_annunci`: timer, documenti, lavori finiti)
  e la registrazione della voce scaduta. Lo stesso difetto c'era per tutte queste frasi, sia al
  turno 0 di una corsia nuova sia dopo che il satellite aveva sentito il nome (si ferma da sé
  fino all'ultimo turno ricevuto) senza una risposta del modello in mezzo. Un `start_turn` in più
  non cambia l'ombra degli eventi (un pezzo senza frasi non conta). Niente regola nel registro:
  non è una regola sul testo.
- **Il satellite finto scarta come il vero**: `prova_giro3.Remota` usa
  `Riproduttore._scartata` (e `sente_il_nome` per il «ferma» senza turno),
  `prove/satellite_finto.py` scarta il turno 0 e i turni fermati (le frasi in `scartate`). Sul
  codice di prima `prova_giro4` fallisce in cinque punti.

**«C'è Locutti.» e «…».** 11:49:12: nel journal `anagrafica_cerca({'testo': '…'})`, «→
(riservato)» e la risposta «…». Sono le **oscurazioni** di un tool riservato (rubrica, documenti
di casa): `Brain._run_tool_una_volta` mostra gli argomenti come «…» e `Ciclo.in_console` la
risposta come «…» (analisi di sicurezza S9, 03/10). Il turno ha la prima frase a 0,98 s e una
frase sentita: con ogni probabilità Calliope ha detto la frase del tool («In rubrica non trovo
…»), senza un secondo giro del modello; nel registro dei turni della DGX `risposta_parole` e la
traccia senza testo lo dicono. Due buchi veri, trovati provando il caso:
- un argomento di **sola punteggiatura** («…», «?», «-») arrivava al tool come testo:
  `tools/dialogo._vuoto` ora lo tratta come vuoto, e il campo obbligatorio ha l'errore
  strutturato del dialogo dei tool (`tool_argomenti_mancanti`, giri di correzione). È la forma
  di un argomento, non il suo significato (principio 10); contrari: «Locutti», «3», «Rossi
  S.r.l.», «è»;
- dopo i giri di correzione finiti, la **passata finale** che rispondeva «…» restava muta (il
  ripiego guardava solo il testo vuoto): ora anche la sola punteggiatura ha «Non ci sono
  riuscita: puoi ripetere la richiesta?» (`risposta_solo_punteggiatura`, `vuoto_ripiego`).
- Prova: `prova_giro4` (A, D).

## Una voce sola, passo 2: l'uscita unica verso la voce (10/10, ramo `eventi-passo-2`)

Passo 2 del § 8 del progetto [`2026-10-10-registro-eventi.md`](../ricerche/2026-10-10-registro-eventi.md)
(§ 3.2). **Niente cambia in ciò che Calliope dice né in ciò che il modello vede** (il contesto resta
la storia di Brain fino al passo 3): cambia da dove passano le frasi.

**Un punto solo.** `calliope/eventi/uscita.py` → `Uscita` (una per voce, quindi per corsia:
`per_voce(speaker)`, la stessa per il ciclo, `main.py` e `rispondi.py`). Le 48 chiamate dirette di
`ciclo.py` e `main.py` (`say`, `say_cached`, `chime`, i suoni, `start_turn`, `wait`) e lo stream di
Brain passano da lì: `di(testo, atto, autore)`, `di_e_aspetta` (le chiusure: il controllo del
satellite di `_di_e_aspetta` è suo, la regola `voce_frase_non_detta` resta del ciclo), `turno()`,
`aspetta()`, `segnale()`, `segnale_suono`, `segnale_ascolto`; il saluto dei satelliti con
`sintetizza_saluto` (atto `saluto_avvio`, fuori conversazione). `prova_uscita_unica` (AST) fallisce
se fuori da `eventi/uscita.py` e `tts.py` qualcuno chiama `say`, `say_cached`, `chime`, `suono`,
`suono_ascolto`, `sintetizza`, `start_turn`, `wait` sulla voce o le sue code, e se lo stream di Brain
si legge fuori da `Ciclo._rispondi` e `Ciclo._ricerca_promessa`. `Speaker.osservatore` (passo 1) non
c'è più: l'ombra la avvisa l'uscita.

**Il detto nasce all'invio.** `Uscita.di` scrive in memoria il `detto_calliope` prima di mandare la
frase al TTS: testo (quello dato a Piper, prima della pronuncia), **atto** dall'elenco chiuso
`tipi.ATTI` (detto da chi chiama, non più ricavato dalla pila delle chiamate), **autore**
(`contenuto` per il modello; `esito` per la frase pronta di un tool e `atto` per il ripiego «Non ci
sono riuscita…», la riga dello sviluppo e la frase della sfida, che Brain marca quando le manda,
`Brain.parlato_marcato`/`_marca`; `atto` per la protezione del guardiano dentro una risposta), canale
(`voce`, `scritto` per una frase scritta, `muta` con la voce muta), fonte (agente, estensione) e
`dopo_chiamate` (quante chiamate dei tool c'erano già nella risposta). Costo ~1,5 µs a frase, nessun
file né database (prova con `open` e `sqlite3` sorvegliati).

**L'elenco degli atti** (`calliope/eventi/tipi.py`, con la categoria e la riga del § 1.1):
`risposta` (contenuto ed esiti), `ripeti`, `riga_sviluppo`, `sfida`, `protezione_risposta` (parole
della risposta); `cortesia`, `protezione_cancello`, `richiesta_tutore`, `annuncio_documento`,
`annuncio_installazione`, `annuncio_lavoro`, `annuncio_estensione`, `annuncio_cassetto`, `modulo`
(oggi nella storia); `annuncio_agenda`, `avviso_tutore`, `errore`, `registrazione`, `saluto`,
`chi_parla`, `senza_domanda`, `protezione`, `fuori_orario` (sentiti e oggi fuori dalla storia: il
loro `non_in_storia:<atto>` è **atteso** fino al passo 3); `attesa_tool`, `attesa_correzione`,
`attesa_coda`, `attesa_contesto`, `attesa_biblioteca`, `attesa_stt`, `annuncio_gioco`, `chiusura`,
`saluto_avvio` (voluti fuori). I nomi del passo 1 (`attesa`, `agenda`, `annuncio`, `cassetto`,
`giochi`) restano per il rigioco degli eventi già su disco. *Storico: fino al passo 1 i motivi si
chiamavano `non_in_storia:agenda`, `non_in_storia:annuncio`…; dal passo 2 `non_in_storia:annuncio_agenda`,
`non_in_storia:annuncio_documento`…* In `calliope stato --turni` un `non_in_storia` di un atto che
dovrebbe essere nella storia (o fuori dall'elenco) ha la sua riga ATTENZIONE; le domande di un atto
hanno sempre un motivo con un nome (`atto_senza_proposta`, mai «altro»).

**Nessuna frase fuori turno** (correzione del quarto giro, ora nell'uscita): un atto detto senza un
turno della voce aperto (turno 0 di una corsia nuova) o in un turno fermato da un'interruzione apre
prima un turno nuovo; le parole di una risposta interrotta restano nel loro turno (la voce le scarta
come prima). Gli `start_turn` espliciti del ciclo restano (`_ascolta`, annunci, chiusure…), come
`uscita.turno()`.

**`voce_fine` e risposta scritta.** A ogni turno nuovo l'uscita dice all'ombra le frasi sentite per
intero (`played`) e l'interruzione del pezzo che si chiude. La risposta scritta sullo schermo
(`rispondi.risposta_scritta`) viene dalle frasi dell'uscita (`Uscita.testo_scritto()`: quelle della
persona in corso, attese escluse), non più da `" ".join(t.said)`: anche per «Ho la foto…» e la frase
di un modulo, ora scritte sullo schermo dopo averle mandate alla voce.

**Il passo 0 e l'ombra.** `parlato` (passo 0) e il confronto dell'ombra leggono gli stessi detti
nati all'invio: atto e autore registrati dove nascono, non ricostruiti (prima l'esito si indovinava a
fine turno confrontando il testo con le frasi pronte nella storia). La proiezione mette le frasi
nella posizione in cui sono andate alla voce rispetto alle chiamate (`dopo_chiamate` del detto,
`passata` della chiamata): la frase detta prima di un tool è il testo del messaggio con la chiamata,
come nella storia di Brain (prima stava dopo i risultati). **Limite**: `split_sentences` tiene una
frase finché non arriva lo spazio dopo il punto, quindi una frase scritta dal modello subito prima di
una chiamata può partire dopo il tool; la proiezione la mette dove si è sentita (il confronto
dell'ombra è per turno e non la conta).

Prove: `prova_uscita_unica` (AST, atti, turni, latenza), `prova_eventi_ciclo` (passo 2: autore e atto
all'invio, posizione delle chiamate, risposta scritta, atti classificati, nessuna frase fuori turno),
adattate `prova_eventi`, `prova_eventi_disco`, `prova_cassetto`. Misure (`prova_satellite` con
Calliope vera, modello e Whisper finti, Piper vero; 3 giri sul ramo e 4 su `main`): `prima_frase_s`
mediana 0,09 s su `main` e 0,08 s sul ramo, prima voce sentita 0,36 → 0,35 s, «dalla fine della
frase alla prima voce» 0,65–0,80 s e 0,68–0,76 s (rumore); `Uscita.di` ~1,5 µs a frase.
