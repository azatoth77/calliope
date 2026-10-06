# Roadmap

*Nata il 06/10/2026 dalla sezione «Roadmap» di CLAUDE.md (proposta P7 di
[`ricerche/2026-10-06-analisi-complessiva.md`](ricerche/2026-10-06-analisi-complessiva.md)).
In alto lo stato e i prossimi passi; poi le proposte delle analisi, ciò che resta da fare per
area e, in fondo, la roadmap com'era, con le voci fatte segnate. Nessuna data promessa.*

## Stato (07/10/2026)

- **Funzionalità nuove congelate** finché la latenza vera della voce non sta stabilmente sotto
  1,2 s di mediana per la prima frase: si fanno solo correzioni, misure e prove. Dopo le
  correzioni del 06/10 la mediana dei turni veri è 1,31 s (p90 3,33) su un campione piccolo, e
  la prova end-to-end dà 1,94–2,03 s di mediana per la prima voce sentita dal satellite
  ([`../prove/manuali/e2e-dgx.md`](../prove/manuali/e2e-dgx.md)).
- Proposte delle due analisi del 06/10: P1–P11 e Q2–Q3, Q5–Q11 fatte; aperte Q1, Q4, Q12–Q14
  (sotto).
- Trascrizione: confronto A / B / B2 / C chiuso il 07/10, si resta su A (correzione spenta);
  C solo con un posto dedicato alla correzione ([`aree/stt-tts.md`](aree/stt-tts.md)).

## Prossimi passi (decisi, dopo il congelamento)

1. **Modulo studio per i ragazzi**: esercizi generati al momento, con la verifica automatica
   delle risposte, in tutte le materie dalle elementari alle superiori; uno strumento di
   **simulazione d'interrogazione** con domande a tempo, registrazione delle risposte e
   valutazione finale di contenuti ed esposizione. Base: compiti guidati e minori
   ([`aree/minori.md`](aree/minori.md)), ricerca in
   [`ricerche/2026-10-07-kolibri.md`](ricerche/2026-10-07-kolibri.md).
2. **Generazione di immagini in locale**: FLUX.2 [klein] 4B (Apache 2.0), con filtri e regole
   per i minori ([`ricerche/2026-10-06-generazione-immagini.md`](ricerche/2026-10-06-generazione-immagini.md)).
3. **Secondo fattore per chi amministra**: conferma dal telefono, chiave vocale
   ([`ricerche/2026-10-06-secondo-fattore.md`](ricerche/2026-10-06-secondo-fattore.md)).
4. **Pannello di amministrazione con le azioni** (oggi il cruscotto è in sola lettura).
5. Poi: **interfono** tra satelliti, **conversazione di stanza** (più persone nella stessa
   conversazione), **mappe e luoghi**, **satellite su Raspberry** (senza PC), **altre fonti
   italiane** nella biblioteca.

**In valutazione (non promesso)**: riscontro emotivo dalla voce durante le sessioni di studio.

**Scartato**: Kolibri come base del modulo studio, perché il catalogo in italiano è quasi vuoto
(sola matematica di Khan Academy) e i contenuti nuovi si creano solo con il servizio online di
Kolibri Studio, contro il principio «niente cloud».

## Subito: le proposte delle analisi del 06/10

Decisione del 06/10: farle tutte, da subito, e congelare le funzionalità nuove (solo
correzioni) finché non sono chiuse.

**Prima analisi** ([`ricerche/2026-10-06-analisi-complessiva.md`](ricerche/2026-10-06-analisi-complessiva.md)):
P1–P11 **fatte** il 06/10. La verifica è nel § 2 della
[seconda analisi](ricerche/2026-10-06-analisi-2.md): P2, P3, P9 e P11 erano fatte solo in
parte, e le Q qui sotto le completano.

| # | Proposta | Stato |
|---|---|---|
| P1 | `stt_correzione` sulla DGX misurata, spenta nel file locale | fatta |
| P2 | Guardiano in parallelo e caldo | fatta; completata da Q3 |
| P3 | Cache del prefisso dopo riavvii | fatta; completata da Q5 |
| P4 | Latenza vera come metrica, con un avviso | fatta |
| P5 | Hook a strati e prove instabili | fatta; completata da Q7 |
| P6 | Guardie doppie tolte, reti con categoria | fatta; corretta da Q2 e Q6 |
| P7 | CLAUDE.md come indice, `docs/aree/` | fatta; tenuta vera da Q8 |
| P8 | `giro` diventa la classe `Ciclo` | fatta; Q10 |
| P9 | Stato della voce per corsia | fatta; completata da Q9 |
| P10 | Costanti comuni (`calliope/testi.py`) | fatta; le 3 copie di `NIENTE` in `politica.py` tolte |
| P11 | Riassunti della compressione con un tempo massimo | fatta; completata da Q11 |

**Seconda analisi** ([`ricerche/2026-10-06-analisi-2.md`](ricerche/2026-10-06-analisi-2.md), § 6):

| # | Proposta | Stato |
|---|---|---|
| Q1 | Un giorno d'uso vero sulla DGX con un elenco di casi | **aperta** |
| Q2 | Sfida dopo una foto o un file | fatta (ramo `correzioni-q`) |
| Q3 | Guardiano che non tace: rilevatore nel registro, guasto = guasto per i minori, schede trattenute | fatta (ramo `correzioni-q`) |
| Q4 | Ollama della DGX: 4 modelli e posto per 3 (`OLLAMA_MAX_LOADED_MODELS=4` o embedding fuori) | **aperta** (serve sudo) |
| Q5 | P3 completo: storia scaldata già compattata | fatta (ramo `correzioni-q`) |
| Q6 | Reti di sicurezza con un effetto vero (`azione_in_sospeso`, `riferire`) | fatta (ramo `correzioni-q`) |
| Q7 | Hook: legami dei tool d'area, import su Linux, prove manuali, salti parziali | fatta (ramo `correzioni-q`) |
| Q8 | Documenti veri e controllati (`prova_docs_aree`) | fatta (ramo `correzioni-q`) |
| Q9 | Voce per stanza con più satelliti nella stessa stanza | fatta (ramo `correzioni-q`) |
| Q10 | «Esci» in una corsia di satellite: si addormenta e continua | fatta (ramo `correzioni-q`) |
| Q11 | Tetto totale al riassunto della compressione | fatta (ramo `correzioni-q`) |
| Q12 | Ridurre la configurazione (−50 campi) | **aperta** |
| Q13 | Spegnere nel 26B le reti «modello» a zero scatti (dopo due settimane di registro) | **aperta** |
| Q14 | Spezzare `Brain._reply` | **aperta** (da sola, a congelamento attivo) |

## Resta da fare (controllato sul codice il 06/10)

**Voce e audio**
- Taratura fine del VAD; falsi risvegli in casa (TV, musica); voci di altri familiari e soglia
  di chi parla da ritarare col secondo familiare.
- Barge-in di livello B completo (DTLN, 4–6 giorni), vedi
  [`ricerche/2026-09-26-cancellazione-eco.md`](ricerche/2026-09-26-cancellazione-eco.md).
- Modello acustico della wake word «computer» (addestramento pronto, da decidere).
- Musica e allarme: requisiti della visione ancora senza codice; decidere la priorità.

**Tool e regole**
- Comandi più frequenti con regole prima dell'LLM («alza», «pausa», «blocca»); `pc_spegni` con
  conferma (non esiste); stato del PC nel messaggio di contesto.
- «Annulla l'ultima modifica» di un documento (le versioni ci sono, il tool no).
- Ponte MCP verso Home Assistant, biblioteca, musica (le estensioni usano già la cornice stdio).
- Recupero dei tool con bge-m3 solo oltre 40–50 tool: oggi i tool sono 65 schemi e la scelta
  regge; da rimisurare se la qualità scende.
- Casa: conferme a secondo fattore per i domini delicati; direzione opposta (HA che usa
  Calliope come agente per i satelliti).

**Biblioteca e installazioni**
- Prima installazione vera dal catalogo (reindirizzamenti di Hugging Face e GitHub, `.sha256`
  di Kiwix, `/api/pull` vero).
- Altre fonti nella ricerca (WikiMed, Wikivoyage, Wikibooks, Wikiversità, Wikisource,
  Gutenberg con l'indice a pezzi).
- Riparazione all'avvio di chi parla e del modello quando mancano.
- Misure del lettore ZIM e dell'indice sullo Spark (`prove/arm/`).

**Schermi, satelliti, telefono**
- Fase 2 (mappe e luoghi) e 3 (percorsi) di
  [`ricerche/2026-10-01-mappe-e-schermi.md`](ricerche/2026-10-01-mappe-e-schermi.md); dalla
  fase 4: DuckDNS per gli schermi, la card di HA.
- Satelliti di stanza senza PC.
- Prove con un iPhone vero (audio, schermo acceso, auto) e su un PC Windows pulito.

**Agenti ed estensioni**
- Isolamento vero della sandbox su Windows (utente dedicato o WSL2).
- I documenti prodotti dagli agenti consegnati al satellite (oggi `LocalDelivery`).
- Estensioni: documenti, messaggi e file ai satelliti dalla porta; estensioni a orario; firma
  delle versioni.
- Node/JavaScript come linguaggio dei programmi in diretta (l'immagine per i test dei giochi c'è).

**Auto-miglioramento** (vedi [`visione.md`](visione.md))
- Set di regressione sulle registrazioni e revisione notturna che **propone** correzioni
  misurate; segnale acustico per le ripetizioni (`revisione.py`).

**Migrazione a RTX Spark (Windows ARM)**
- Modelli MoE più grandi e verifica di ogni dipendenza su Windows ARM.

## Storico: la roadmap di CLAUDE.md al 06/10

1. ~~Primo test reale~~ (fatto). Restano la taratura fine del VAD e la scelta dei
   modelli (Whisper small / medium / large-v3-turbo; LLM 4B contro 7–8B).
2. ~~Configurazione esterna e divisione in package~~ (fatta il 26/09): package
   `calliope/` (`main`, `audio`, `stt`, `tts`, `wakeword`, `brain`, `config`, `tools/`…),
   configurazione in `calliope.yaml`. Le prove in `prove/` importano da `calliope.*`.
3. ~~Wake word dedicata~~ (fatta il 24/09, vedi
   [`docs/ricerche/2026-09-24-wake-word.md`](ricerche/2026-09-24-wake-word.md)).
   Restano la misura dei falsi risvegli in casa (TV, musica), le voci di altri familiari
   ed eventualmente la personalizzazione all'arruolamento.
4. **Barge-in**: livello A fatto il 26/09. `Listener.watch_for_name` ascolta solo la
   wake word mentre Calliope parla. `Speaker.interrupt` la ferma entro 100 ms, e
   `Brain.record_interruption` lascia nella storia solo le frasi pronunciate. Livello B
   leggero fatto il 26/09: `Listener.measure_echo` durante il saluto decide se attivarlo.
   Poi `watch_for_name(voice_ok=…)` controlla l'impronta dopo 0,8 e 1,6 s di parlato:
   solo le persone registrate interrompono, non TV né ospiti. Livello B completo (DTLN,
   4–6 giorni) rimandato, vedi
   [`docs/ricerche/2026-09-26-cancellazione-eco.md`](ricerche/2026-09-26-cancellazione-eco.md).
5. **Tool / function calling**: fatti i tool nativi di base (v0.3) e la memoria per
   persona (26/09). Restano il ponte MCP (Home Assistant, biblioteca, musica) e le
   azioni sensibili con conferma. **Molti tool** (ricerca del 26/09,
   [`docs/ricerche/2026-09-26-tool-e-agenti.md`](ricerche/2026-09-26-tool-e-agenti.md)):
   gemma4:e4b sceglie bene anche con 40 tool piatti (99 %). Regola: elenco fisso per
   livello fino a 25–40 tool, parti variabili subito prima della domanda. Recupero con
   bge-m3 (in `ToolRegistry`) solo oltre 40–50 o per le entità di casa. Agenti solo per i
   lavori a più passi, con un arbitro davanti a Ollama (senza, la voce aspetta 11 s).
   Fatti il 26/09: `calcola`, timer e promemoria (durate e orari convertiti in Python da
   `tempi.py`) e la biblioteca offline (`biblioteca_cerca`, decisione B della visione),
   poi liste, appuntamenti e memoria della casa, e il PC a voce (punto 1 della roadmap 5.3
   di [`docs/ricerche/2026-09-26-controllo-pc.md`](ricerche/2026-09-26-controllo-pc.md):
   8 tool `pc_*` sul portatile, esecutore in processo). Fatti il 27/09 i documenti Word,
   Excel e PDF a voce (`documento_crea`, `documento_modifica`, scrittura con una seconda
   richiesta a Ollama e output strutturati); restano la consegna al PC remoto
   (`LocalDelivery` → «ricevi file» dell'esecutore), l'arbitro davanti a Ollama per le
   generazioni in secondo piano, *[fatti: `RemoteDelivery` il 03/10, arbitro il 02/10 e pausa di vLLM il 04/10]* «annulla l'ultima modifica» (le versioni ci sono) e i
   modelli personali (carta intestata). *[fatti il 03/10: ufficio con docxtpl e python-pptx]* Per il PC restano l'esecutore
   separato via WebSocket (punto 2) *[fatto il 03/10: esecutore remoto sul satellite]*, `pc_spegni` con conferma a regole, lo stato del PC
   nel messaggio di contesto e le regole prima dell'LLM per «alza», «pausa», «blocca».
   Fatta il 01/10 la casa via Home Assistant (direzione Calliope → HA: `casa_comando`,
   `casa_stato`, `casa_integrazione`), provata solo con l'HA finto. *[Superato: HA vero provato il 01/10 sera.]* Restano: la prova a
   casa (sonda, tempi del Raspberry, nomi e alias veri) *[fatta il 01/10 sera]*, i comandi più frequenti con regole
   prima dell'LLM, le conferme a secondo fattore per i domini delicati e la direzione
   opposta (HA che usa Calliope come agente per i satelliti: l'interfaccia `HomeBackend`
   non la impedisce). Fatti il 01/10 il registro delle capacità (`calliope_stato`,
   `python -m calliope.stato`) e le installazioni a voce dal catalogo. Restano: la prima
   installazione vera (reindirizzamenti di Hugging Face e GitHub, `.sha256` di Kiwix), le
   altre fonti in più nella ricerca (WikiMed e Wikivoyage con l'instradamento per tema,
   Wikibooks e Wikiversità con un peso; Wikisource e Gutenberg con l'indice a pezzi di
   ~2 000 caratteri per i testi lunghi: ricerche/2026-10-01-biblioteca-senza-libzim.md),
   la riparazione di chi parla e del modello all'avvio quando mancano (oggi Calliope non
   parte: si installano da terminale). Fatte il 01/10 la biblioteca senza libzim (lettore
   ZIM in puro Python e indice SQLite FTS5, azione `biblioteca_indice`) e Wikiquote per le
   citazioni; resta da misurare sullo Spark (`prove/arm/`).
   Fatta il 02/10 la fase 1 degli **schermi** (server delle schede, pagina kiosk, abbinamento,
   visibilità, schede dei tool, `schermo_mostra`, `schermo_gestisci`). Restano, dal rapporto
   [`docs/ricerche/2026-10-01-mappe-e-schermi.md`](ricerche/2026-10-01-mappe-e-schermi.md):
   fase 2 mappe e luoghi (PMTiles servite con le Range da `schermi/server.py`, scheda `mappa`
   in `schede.py` e nella pagina, indice SQLite dei luoghi, GeoNames, `luoghi_cerca`,
   `mappa_mostra`), fase 3 percorsi (Valhalla, GraphHopper su ARM), fase 4 più schermi e
   satelliti (HTTPS con DuckDNS *[HTTPS con certificato proprio fatto il 02/10, CA di casa il 03/10; DuckDNS no]*, la stanza dal satellite in `Mittente.stanza`, lo schermo
   personale del PC tramite l'esecutore, la card di HA). Anche: il kiosk di Edge
   all'avvio di Calliope (la scheda del timer che scade c'è dal 02/10; manca quella della
   lista cambiata da un'altra stanza verso gli schermi delle altre stanze).
   Fatti il 02/10 gli **agenti in secondo piano** (`calliope/agenti/`: tunnel SSH verso la
   DGX, ciclo d'agente, sandbox, arbitro, `delega_lavoro`, `lavori_stato`,
   `lavori_annulla`, capacità «agenti», `python -m calliope.agenti --prova`, banco
   `prove/prova_lavori.py`). Restano: la prima prova sulla DGX vera (passi in
   `prove/LEGGIMI.md`) e il banco contro `qwen3.6:35b`; *[fatti il 02/10: banco codice 11/12, documenti 10–11/12 con qwen3.6 su vLLM]* llama-server per l'agente (bug
   #16383 di qwen3.6 nel parser di Ollama, prefill a pezzi con `-b 512`); *[superato il 02/10: l'agente usa vLLM]* le domande a metà
   lavoro e i file della persona all'agente (fatti il 03/10) da misurare con il modello vero;
   un isolamento vero della sandbox su Windows *[ancora aperto; dal 03/10 su Windows il codice dell'agente non si esegue]* (utente dedicato o
   WSL2: sulla DGX c'è il container dal 03/10);
   l'esecutore remoto per consegnare i risultati sul PC di chi li ha chiesti. *[fatto il 03/10 per i lavori sui file della persona; i documenti degli agenti usano ancora `LocalDelivery`]*
6. **Auto-miglioramento** (vedi `docs/visione.md`): registro dei turni in JSONL,
   rilevamento delle frasi ripetute come segnale di errore di trascrizione, set di
   regressione sulle registrazioni, revisione notturna che **propone** correzioni
   misurate. Il prompt, il codice e i permessi non si toccano mai da soli.
7. Migrazione a **RTX Spark**: modelli MoE più grandi e verifica di ogni dipendenza
   su Windows ARM. Gli agenti non aggiungono dipendenze native (job object con ctypes,
   OpenSSH di Windows c'è anche su ARM64); con la DGX in casa basta `collegamento:
   diretto` (o `agenti_url`), senza tunnel.
   Fatto il 02/10 il **satellite minimo** (`calliope/satellite/`: il portatile come
   microfono, casse e schermo di Calliope sulla DGX), il 03/10 l'esecutore remoto del PC
   sulla stessa connessione (`pc_*` e consegna dei documenti al portatile). Restano: la prova con la DGX vera
   (`prove/LEGGIMI.md`) *[fatta dal 02/10]*, più satelliti attivi insieme (una conversazione per stanza) *[fatto il 06/10: corsie]*,
   HTTPS per gli schermi *[fatto il 02/10]*, satelliti di stanza senza PC.
