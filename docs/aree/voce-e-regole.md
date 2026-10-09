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
| Wake word testuale (ripiego, conferma, estrazione della richiesta), uscita, stop, cortesia | difflib sulla trascrizione | `calliope/wakeword.py` → `find_wake_word` (più parole, `start_only`), `exit_intent` / `exit_request`, `is_stop`, `closing_kind`, `said_name`; `calliope/cortesia.py` → `Cortesia` («Prego!», «Bene!» per tono); le parole in `Config.wake_names` (`wake_word`, dal 04/10) |
| LLM + tool calling | Ollama, API nativa `/api/chat` (httpx) o `/v1` (`openai`) | `calliope/brain.py` → `Brain`, `OllamaBackend`, `OpenAIBackend`; modello della voce in una riga, `llm_profilo` (`calliope/config.py` → `PROFILI_LLM`, con le reti adatte in `llm_reti_spente`); banco `prove/prova_regressione.py` |
| Tool nativi | — | `calliope/tools/` (`spec.py`, `registry.py`, `builtin.py`); argomenti che nominano qualcosa `ToolSpec.nomi` e la loro misura in Brain (`_argomenti_inizio`, `_argomenti_fine`, `argomenti_per_registro`, dal 08/10: [stt-tts](stt-tts.md)); forma degli argomenti ricondotta a quella del tool `ToolSpec.prepara` (dal 08/10) |
| Dati del turno (contesti prima della domanda, mai nel prompt di sistema) | — | `calliope/brain.py` → `TURN_CONTEXT_MSG`, `PENDING_MSG`, `AGENDA_MSG`, `SOSPESO_ALTRUI_MSG`, `EST_NOMINATA_MSG`, `RIFIUTO_MSG` (dal 09/10); modalità sviluppo `calliope/sviluppo.py` → `SVILUPPO_MSG`, `Sviluppi.dati_turno` (dal 08/10) |
| «La frase è rivolta a Calliope?» in compagnia (dal 09/10, in ombra) | Ollama, output strutturato sul modello del rilevatore di pericolo | `calliope/rivolta.py` → `Giudice`, `etichetta`; `Brain.dimentica_ultimo_turno`; la compagnia è in [stt-tts](stt-tts.md) |
| Pulizia output | regex | `calliope/brain.py` → `ThinkFilter`, `TextCallGuard`; `calliope/tts.py` → `split_sentences`, `clean_for_speech` |
| Configurazione | dataclass + YAML (PyYAML) | `calliope/config.py` → `Config`, `load_config`, `VOICE_MAP`; file `calliope.yaml` |
| Registro dei turni | JSONL, un file al giorno in `registro/` | `calliope/turnlog.py` → `TurnLog`; analisi con `revisione.py` |
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
  `lavori_conferma_implicita`, `lavori_agente_irraggiungibile`; dal 03/10 `schermo_personale_senza_codice`, `schermo_personale_con_codice`, `schermo_proprietario_permesso`. Solo nomi: per gli ospiti il
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
  riceve tool e domanda dell'ultima ricerca e l'indicazione: per approfondire, dire di più o
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
