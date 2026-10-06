# Calliope — architettura dei tool

*Proposta del 23 settembre 2026. Fonti: [`docs/visione.md`](visione.md) (principi 5, 6, 9) e
[`ricerche/2026-09-21-orchestrazione-agenti.md`](ricerche/2026-09-21-orchestrazione-agenti.md).*

## 1. Due famiglie: nativi e MCP

Come OpenCode e Claude Code, Calliope distingue due famiglie di tool:

| | Tool **nativi** | Tool **MCP** |
|---|---|---|
| Cosa | la **specificità di Calliope** | l'**ampliamento** verso il mondo |
| Dove vive | nel processo Python | fuori, come server |
| Esempi | identità, voce, ascolto, casa, memoria, ora | Home Assistant, biblioteca Kiwix, musica, file, web |
| Si aggiunge | con un cambio di codice | collegando un server |

**Criterio.** Se il tool ha bisogno dello **stato interno di Calliope** (microfono,
voiceprint, voce TTS, sessione) o di **dati che Calliope possiede** (memoria, stato di
casa), è **nativo**. Se è un **servizio esterno** che parla un protocollo, è **MCP**.

**Perché gli interni non passano da MCP:**

- **Latenza** — un hop stdio/HTTP in più sul percorso vocale, dove ogni ms conta.
- **Accesso** — un server MCP esterno non vede il voiceprint né il microfono del processo.
- **Dipendenze** — l'SDK `mcp` richiede `pyjwt[crypto]` → `cryptography`, che dalla 46.0.4
  non ha wheel ARM64 (vedi la ricerca sull'orchestrazione). Lo Spark eredita il blocco.
- **Controllo** — i nativi si filtrano per livello *nel codice* (principio 9 della visione).

## 2. Componenti

Struttura del package dal 26/09/2026 (roadmap 2):

```
calliope/                 # package: python -m calliope
├── main.py               # ciclo principale
├── config.py             # Config, load_config (calliope.yaml), VOICE_MAP, costanti
├── brain.py              # ciclo di tool calling in streaming
├── tools/
│   ├── spec.py           # ToolSpec, ToolContext
│   ├── registry.py       # filtro per livello, esecuzione
│   ├── builtin.py        # i tool nativi di Calliope
│   ├── pc.py             # i tool pc_* (PC a voce)
│   ├── documenti.py      # documento_crea, documento_modifica
│   ├── casa.py           # casa_comando, casa_stato, casa_integrazione
│   ├── schermi.py        # schermo_mostra, schermo_gestisci
│   ├── agenti.py         # delega_lavoro, lavori_stato, lavori_annulla
│   └── stato.py          # calliope_stato, installa_proponi, installa_avvia, installa_gestisci
├── pc/                   # capacità dei PC: PCExecutor (base.py), LocalWindowsExecutor (windows.py)
├── documenti/            # Word, Excel, PDF: formato.py (JSON e validazione), scrittore.py
│                         # (LLM), render.py, consegna.py (dove va il file), servizio.py
├── casa/                 # la casa: HomeBackend (base.py), HomeAssistantBackend
│                         # (homeassistant.py), regole.py, parole.py, errori.py, guida.py,
│                         # diagnose
├── schermi/              # gli schermi: archivio.py (abbinati, codici), hub.py (chi riceve
│                         # cosa), schede.py, server.py (Starlette + uvicorn, SSE), pagina/
├── agenti/               # lavori in secondo piano: impostazioni.py (dgx.yaml, agenti_url),
│                         # tunnel.py (ssh -N -L), winjob.py, remoto.py (Ollama dell'agente),
│                         # arbitro.py, sandbox.py + _avvio.py, ciclo.py, modelli.py (template),
│                         # servizio.py (coda, proposta, risultati, annuncio), __main__.py (--prova)
├── capacita.py           # registro delle capacità: stato, motivo, prossimo passo
├── stato.py              # python -m calliope.stato (tabella, --json, --installa)
├── installa/             # installazioni dal catalogo: catalogo.py, scarica.py, servizio.py
├── audio.py              # ascolto, VAD, barge-in
├── stt.py                # trascrizione
├── tts.py                # voce
├── wakeword.py           # wake word acustica e testuale
├── speaker_id.py         # chi parla
├── memory.py             # memoria per persona (tool ricorda/dimentica)
├── agenda.py, tempi.py   # timer, promemoria, appuntamenti
├── liste.py              # liste della casa (spesa, cose da fare…)
└── turnlog.py            # registro dei turni
```

## 3. ToolSpec

```python
@dataclass
class ToolSpec:
    name: str
    description: str
    parameters: dict          # JSON schema, campi vincolati
    func: Callable            # funzione Python nativa
    risk: str                 # "lettura" | "azione" | "sensibile"
    levels: frozenset[str]    # {"ospite", "familiare", "amministra"}
    requires_internet: bool   # principio 5
    announce: tuple[str, ...] # frasi d'attesa dei tool lenti
    segreti: tuple[str, ...]  # argomenti mai scritti nei log (il codice di uno schermo)
```

`ToolContext` porta ai tool ciò che serve loro del processo (config, registro utenti,
contesto speaker, oggetto voce). Le funzioni dei tool ricevono `ctx` come primo argomento
e restituiscono un `dict` serializzabile.

## 4. Registro e filtro

- `schemas(online)` → gli schemi che vede il modello: **tutti i tool, uguali per ogni
  livello** (dal 03/10), nell'ordine di registrazione. Prompt di sistema e schemi formano un
  prefisso identico byte per byte per ospite, familiare e chi amministra (prova a secco in
  `prova_brain.py`): con un elenco per livello, quando cambiava chi parla Ollama doveva
  rileggere ~6000 token (+1,1–1,5 s col 4B, +2 s col 26B,
  [`ricerche/2026-10-03-modello-davanti.md`](ricerche/2026-10-03-modello-davanti.md)).
  (La proposta del 23/09 diceva 5–10 tool per livello; la ricerca del 26/09 ha misurato che
  gemma4:e4b sceglie bene anche con 40 tool piatti.)
- `schemas_for(livello)` / `allowed(nome, livello)` → i **permessi**: cosa il registro
  esegue a quel livello. Servono alle prove e a Brain (la spinta sui file solo se il livello
  può cercarli), non al prompt.
- `call(nome, argomenti, ctx, livello)` → ricontrolla il permesso, esegue la funzione nativa
  e restituisce JSON; un errore non solleva un'eccezione verso il modello, torna come
  risultato da leggere.
- Senza rete (`online=False`) i tool con `requires_internet=True` **spariscono
  dall'elenco** (principio 5) e il resto continua a funzionare.

## 5. Livelli e permessi

Principio 9 della visione: ospite → familiare → chi amministra.

| Livello | Quando | Vede |
|---|---|---|
| `ospite` | voce non riconosciuta (default) | sola lettura |
| `familiare` | voce riconosciuta | voce, azioni a basso rischio |
| `amministra` | `Primo`/`Prima` (il primo utente) | tutto |

Fino al 02/10 i tool vietati non venivano mostrati al modello. Dal 03/10 il modello li vede
tutti (prefisso unico, vedi §4) e **il permesso lo decide solo il codice**, a ogni
esecuzione: `ToolRegistry.call` rifiuta un tool non ammesso con `ok: false`, «NIENTE: l'azione
NON è stata eseguita» e una frase pronta (`REFUSAL`, come `risposta_finale`: il turno finisce
senza un'altra passata del modello, che con un semplice «non permesso» diceva lo stesso «ho
registrato…»). All'ospite: «Mi dispiace, questo posso farlo solo per chi vive in casa, e la tua
voce non la riconosco.»; al familiare con un tool di chi amministra: «Mi dispiace, questo può
chiederlo solo chi amministra Calliope.». Il risultato aggiunge «per le altre richieste chiama
i tool come sempre» (un tool fallito non deve avvelenare la conversazione) e il registro dei
turni ha la regola `permesso_livello`. Anche `casa_comando` per un ospite fuori da
`casa_ospite_domini` usa la stessa frase. Nessuna frase furba può far eseguire un tool
vietato: il controllo non dipende da ciò che il modello vede. Ciò che dipende da chi parla
(nome, ricordi, fatti della casa) va nei messaggi subito prima della domanda, mai nel
prefisso; le descrizioni dei tool non contengono dati personali. Per le azioni sensibili
servirà un secondo fattore (vedi visione).

## 6. Ciclo di tool calling

1. Python identifica lo speaker (CAM++) → **livello**.
2. Manda al modello gli stessi schemi per ogni livello; il livello serve a `call`.
3. LLM risponde in **streaming**: il testo va subito al divisore di frasi → TTS.
4. Accumula i `tool_calls`, esegue, reimmetti i risultati, ripete (tetto `max_tool_turns`).
5. `tool_choice` non è supportato da Ollama: **il modello decide da solo** se chiamare un
   tool. Per questo i tool nativi vanno tenuti semplici, con campi vincolati.

### 6.1 Contratto dei risultati (proposta del 03/10, da fare)

L'analisi del comportamento del 03/10 ha contato le forme dei risultati: le letture non
hanno `ok` né `conferma` (`ora_attuale` → `{ora, fuso}`, `agenda_elenca` → `{numero, voci}`),
il testo pronto si chiama `conferma`, `da_dire` (solo `calcola`) o `risposta_finale`, gli
errori sono `{errore}`, `{ok: false, errore}`, `{ok: false, errore, cosa_fare}` o `{ok:
false, fatto: "NIENTE…", motivo, per_il_resto}`. Brain oggi le legge solo attraverso due
adattatori (`brain._result_ok`, `brain._result_text`); il contratto unico proposto:

| Campo | Obbligatorio | Per chi | Significato |
|---|---|---|---|
| `ok` | sì | modello e Brain | riuscito o no |
| `da_dire` | sì | modello e Brain | la frase per la voce, numeri in cifre |
| `dati` | no | modello | i dati grezzi (elenchi, passaggi) |
| `errore`, `cosa_fare` | solo se `ok` è false | modello | perché, e cosa chiedere |
| `fatto` | no | modello | `eseguito`, `proposto`, `niente` |
| `finale` | no | Brain | `da_dire` chiude il turno (oggi `risposta_finale`) |
| `in_sospeso`, `scheda`/`schede`, `riferimento` (`{tipo: casa\|agenda, …}`) | no | Brain | tolti prima del modello |

Il passaggio è meccanico (un `ToolResult` in `tools/spec.py`, i tool uno per volta, un
controllo nelle prove a secco), ma tocca tutti i tool e le prove con Ollama che leggono
`conferma`: si fa in un lavoro a parte, misurato con il banco di regressione.

## 7. Tool nativi (primo passo)

| Tool | Livello | Rischio | Cosa |
|---|---|---|---|
| `chi_parla` | ospite | lettura | chi parla adesso (nome, livello, certezza) |
| `elenca_voci` | ospite | lettura | le voci TTS disponibili |
| `ora_attuale` | ospite | lettura | ora locale |
| `data_oggi` | ospite | lettura | data locale |
| `calcola` | ospite | lettura | conti esatti su un'espressione (valutatore `ast`), con `da_dire` per la voce |
| `biblioteca_cerca` | ospite | lettura | fatti precisi da Wikipedia offline (`biblioteca.py`); registrato solo se ci sono i file ZIM. Con Wikiquote scaricata e indicizzata (01/10) anche citazioni e «chi ha detto…?», e la descrizione lo dice (`biblioteca_spec(citazioni=True)`) |
| `timer_imposta` | ospite | azione | timer della casa; durata come detta a voce (`tempi.py`) |
| `promemoria_imposta` | familiare | azione | promemoria personale; orario come detto a voce |
| `appuntamento_aggiungi` | familiare | azione | appuntamento personale, con un avviso automatico `appuntamento_anticipo_min` prima (60) se c'è ancora tempo |
| `appuntamenti_elenca` | familiare | lettura | appuntamenti di un giorno o intervallo detto a voce (`tempi.parse_day_range`); vuoto = 7 giorni |
| `agenda_elenca` | ospite | lettura | timer attivi, promemoria di chi parla e appuntamenti dei prossimi 2 giorni |
| `agenda_annulla` | ospite | azione | annulla un timer, un promemoria o un appuntamento (con il suo avviso) per descrizione |
| `elenca_utenti` | familiare | lettura | utenti registrati |
| `cambia_voce` | familiare | azione | cambia la voce di chi parla |
| `rinomina_interlocutore` | familiare | azione | rinomina chi parla |
| `registra_utente` | amministra (dal 05/10, con la frase di sfida) | azione | avvia l'arruolamento di una persona nuova con la data di nascita (o «maggiorenne») e i tutori; un minore ha il preset della sua fascia (`calliope/minori.py`) |
| `compiti_aiuto` | familiare (solo con un minore in casa; agisce per i minori con i compiti guidati) | lettura | registra l'esercizio, controlla la risposta con il valutatore di `calcola`, mai la soluzione prima di 5 errori, poi l'avviso ai tutori |
| `minore_gestisci` | familiare (il codice: un tutore o chi amministra, dalla voce) | azione | preset di un minore: stato, imposta, orari, estensioni, autorizzazione a tempo, nascita, tutori, riepilogo dei compiti |
| `ricorda` | familiare | azione | salva un fatto su chi parla (memoria persistente, `memory.py`); con `per_tutti` è un fatto della casa (persona `casa`), visto da tutti i familiari |
| `dimentica` | familiare | azione | toglie un fatto (o «tutto»): prima tra quelli di chi parla, poi tra quelli della casa |
| `lista_aggiungi` | familiare | azione | aggiunge voci a una lista della casa (`liste.py`), senza doppioni; si annota chi le ha aggiunte |
| `lista_leggi` | familiare | lettura | legge una lista con il conteggio (le prime 8 e «e altre N») |
| `lista_togli` | familiare | azione | toglie voci con confronto tollerante; «tutto» svuota la lista |
| `pc_stato` | familiare | lettura | volume, musica, luminosità, batteria, bloccato; `programmi_aperti` solo proprietario o chi amministra |
| `pc_volume` | familiare (ospite se `pc_ospite_volume_media`) | azione | alza, abbassa, imposta, muto, riattiva; valori come detti («un po'» = `pc_passo`), tra 0 e 100 |
| `pc_media` | familiare (ospite se `pc_ospite_volume_media`) | azione | riproduci, pausa, avanti, indietro sulla sessione multimediale di Windows |
| `pc_luminosita` | familiare | azione | alza, abbassa, imposta la luminosità dello schermo |
| `pc_apri_app` | familiare | azione | apre un'app del catalogo `pc_app` (enum); mai un comando dal modello |
| `pc_blocca` | familiare | azione | blocca lo schermo |
| `pc_cerca_file` | proprietario o chi amministra | lettura | Windows Search sulla cartella dell'utente; periodo detto a voce (`tempi.parse_past_range`) |
| `pc_apri_file` | proprietario o chi amministra | azione | apre il risultato n dell'ultima ricerca della stessa persona (15 minuti); anche chi non è proprietario, se è un documento appena fatto preparare da lui |
| `documento_crea` | familiare | azione | documento Word, Excel o PDF nuovo; il modello passa formato e richiesta come detta, il testo lo scrive una seconda richiesta a Ollama (`calliope/documenti/`) |
| `documento_modifica` | familiare | azione | cambia l'ultimo documento di chi parla («cambia la data in 15 ottobre», «aggiungi una riga: internet 30»); il file si riscrive con lo stesso nome |
| `casa_comando` | familiare (ospite per i domini di `casa_ospite_domini`) | azione | un comando per la casa in una frase breve nella forma di Home Assistant («accendi la luce della cucina»); verifica a secco, regole di Calliope, poi l'agente integrato di HA; la sua risposta è la `risposta_finale` |
| `casa_stato` | familiare (ospite come sopra) | lettura | com'è la casa dagli stati delle entità esposte, senza richieste a HA: «temperatura in camera», «cosa c'è acceso», «porta del garage» |
| `casa_integrazione` | familiare | lettura | a che punto è il collegamento con HA e il prossimo passo (dettagli solo a chi amministra); con `per_iscritto` la guida in PDF o Word, da un testo fisso |
| `calliope_stato` | ospite | lettura | «cosa sai fare?», «cosa manca?», «perché non va…?» dal registro delle capacità: chi amministra sente motivo e prossimo passo, i familiari cosa funziona, gli ospiti cosa possono chiedere; `risposta_finale` |
| `installa_proponi` | familiare (il codice accetta solo chi amministra, riconosciuto dalla voce nel turno) | lettura | proposta di un'azione del catalogo (enum): dimensione, spazio libero, tempo, internet, domanda finale; prerequisiti controllati; non scarica niente |
| `installa_avvia` | amministra | sensibile | avvia l'azione proposta nel turno **prima** alla stessa persona; senza offerta valida rifiuta |
| `installa_gestisci` | familiare (annullare solo chi amministra) | azione | «a che punto è?», «annulla il download» |
| `schermo_mostra` | ospite (il codice decide cosa può vedere) | lettura | «mostramelo sullo schermo», «metti la lista sullo schermo», «fammelo leggere», «togli dallo schermo»: `cosa` in enum (ultima, risposta, lista, timer, promemoria, documento, casa, niente); la scheda la costruisce il codice, la frase dice cosa è successo davvero (`risposta_finale`) |
| `schermo_gestisci` | amministra | azione | abbina (codice di 6 cifre, stanza, personale), scollega, elenca gli schermi; il codice è un argomento segreto (`ToolSpec.segreti`) |
| `delega_lavoro` | familiare (il codice: solo chi amministra, `agenti_livello_codice`, riconosciuto dalla voce nella frase) | azione | affida a un agente in secondo piano un lavoro lungo il cui risultato è un programma o un file complesso: `tipo` codice, documento (anche da un `modello`), ricerca, altro; `compito` con i dati detti. I lavori costosi chiudono con «Procedo?» (azione in sospeso) e partono solo con `proposta` = l'id del lavoro, nella risposta dopo, della stessa persona; `risposta_finale` |
| `lavori_stato` | familiare | lettura | a che punto sono i lavori (passo dell'agente, coda, ultimo finito) |
| `lavori_annulla` | familiare (gli altrui solo chi amministra) | azione | ferma il lavoro in corso o in coda, subito (stream chiuso, sandbox fermata) |

I tool `pc_*` ci sono solo se il PC c'è (`calliope.pc.load_pc`: Windows e librerie
presenti), e ciascuno solo se il PC ha quella capacità. «Proprietario» è un controllo nel
codice, non un livello: i tool restano visibili a tutti i familiari, così il prefisso del
prompt non cambia, e chi non è `pc_proprietari` (nome o id) riceve «NON è stata eseguita».
A schermo bloccato l'esecutore rifiuta app, file, ricerca e programmi aperti. Il parametro
`pc` compare solo con più di un PC. Dettagli: `docs/ricerche/2026-09-26-controllo-pc.md`.

I tool `documento_*` ci sono solo se c'è almeno una delle librerie (python-docx, openpyxl,
fpdf2; `calliope.documenti.load_documenti`), con l'enum dei formati disponibili. Il modello
non scrive il documento: passa una richiesta breve e il servizio chiede il JSON a Ollama con
lo schema degli output strutturati, lo valida e fa il file. Il tool aspetta il file
`documenti_attesa_s` (4 s); oltre, risponde «te lo preparo» e Calliope annuncia il documento
pronto come un timer (segnale acustico, `due_event`). Il risultato ha `risposta_finale`: il
`Brain` la dice così com'è e chiude il turno senza un'altra passata del modello, che
aspetterebbe Ollama occupato con il documento. Ogni documento ha un proprietario (id del
profilo): il registro li rifiuta all'ospite, e nessuno modifica il documento di un altro. Il file
appena scritto diventa l'«ultima ricerca» della persona sul PC: «aprilo» è
`pc_apri_file(1)`.

I tool `casa_*` (01/10/2026) parlano con un'interfaccia di capacità, `HomeBackend`
(`calliope/casa/base.py`): entità esposte con nome, stanza, tipo e stato, e comandi detti
come frase. L'adattatore di oggi è Home Assistant (`homeassistant.py`): una connessione
WebSocket tenuta aperta, gli stati delle sole entità esposte ad Assist aggiornati da
`subscribe_entities`, e i comandi in due tempi: `conversation/agent/homeassistant/debug`
riconosce la frase senza eseguirla, le regole di Calliope (`regole.py`) decidono, poi
`conversation/process` con l'agente integrato (`conversation.home_assistant`). Le regole:
- solo entità esposte: un bersaglio fuori elenco blocca il comando;
- serrature, allarme, cancello e porta del garage (`casa_sola_lettura_domini`,
  `casa_sola_lettura_classi`) si leggono e non si comandano: l'agente di HA non chiede
  conferme né PIN;
- scene, script e automazioni solo se sono in `casa_consentiti`; frasi e automazioni
  personalizzate della casa mai;
- l'ospite niente, salvo i domini di `casa_ospite_domini` (predefinito vuoto);
- ciò che non è della casa (ora, timer, liste) torna al modello, che ha i suoi tool.
Senza indirizzo o token `casa_comando` e `casa_stato` non ci sono; `casa_integrazione` sì,
per spiegare cosa manca. Il nucleo non nomina Home Assistant: un altro sistema domotico
sarebbe un altro adattatore.

Le capacità e le installazioni (01/10/2026). `calliope/capacita.py` tiene per ogni capacità
(modello, trascrizione, voce, wake word, chi parla, audio, memoria, biblioteca, PC,
documenti, casa, schermi, agenti) uno stato tra `attiva`, `da_configurare`, `mancante`, `guasta`, con motivo,
prossimo passo per la voce e dettagli per chi amministra. I caricamenti (`load_biblioteca`,
`load_pc`, `load_documenti`, `load_casa`, `load_wake_detector`, `Transcriber`) vi segnalano
il loro stato invece di stampare ognuno a modo suo; all'avvio si stampa un riassunto, da
terminale `python -m calliope.stato` dà la tabella (anche `--json`), a voce `calliope_stato`.
Il prompt di sistema riceve dal registro un elenco breve e stabile di cosa c'è e cosa no
(`capacita.testo_prompt`), contro le capacità inventate.

Le installazioni (`calliope/installa/`) si fanno **solo dal catalogo nel codice**: file ZIM
italiani di Kiwix (versione, dimensione e checksum risolti dall'indice e dai `.sha256`
ufficiali), le quattro voci ufficiali di Piper, il modello CAM++, il modello di Ollama in
`llm_model` (`/api/pull`), l'indice di ricerca della biblioteca (`biblioteca_indice`, solo
lavoro locale: SQLite FTS5 accanto ai file ZIM, costruito anche da solo dopo ogni download di
Wikipedia ridotta o Vikidia), la pulizia dei file superati. Il modello sceglie solo l'id
dell'azione. Mai pip, mai `calliope.yaml` o `calliope.locale.yaml`: lì Calliope dice cosa
fare. Il flusso è in due turni: `installa_proponi` controlla i prerequisiti e chiude con una
domanda (azione in sospeso per `installa_avvia`); `installa_avvia` parte solo se c'è
un'offerta della stessa persona per la stessa azione fatta nella risposta precedente. Il
download va in secondo piano (ripresa con Range su `.part`, checksum, spostamento atomico),
si annuncia con il segnale acustico e, quando si può, si attiva senza riavvio (la
biblioteca si riapre e `biblioteca_cerca` compare). Lo stesso codice da terminale:
`python -m calliope.stato --installa <azione>`.

Gli **schermi** (02/10/2026, fase 1 di
[`ricerche/2026-10-01-mappe-e-schermi.md`](ricerche/2026-10-01-mappe-e-schermi.md)). Un
server Starlette + uvicorn (senza extra, puro Python) gira in un thread di Calliope e serve
una pagina kiosk; gli schermi abbinati la ricevono in SSE. Le **schede** non le scrive il
modello: un tool mette nel suo risultato `scheda` (o `schede`), costruita dal codice
(`calliope/schermi/schede.py`), e `Brain._run_tool` la **toglie prima che il risultato vada al
modello** e la passa a `Schermi.invia`, che non blocca (`call_soon_threadsafe` +
`put_nowait`): la scheda arriva allo schermo prima della risposta, e la voce non la aspetta
mai. Le mettono: `lista_*`, `timer_imposta`, `promemoria_imposta`, `agenda_*`,
`appuntamento_*`, `calcola`, `biblioteca_cerca`, `casa_stato`, `documento_*` (l'anteprima,
anche a file pronto in secondo piano). Ogni scheda ha una visibilità decisa nel codice:
`pubblica` (timer, calcoli, biblioteca) su ogni schermo della stanza, `casa` (liste, stato
della casa) solo se chi parla è riconosciuto, `personale` (promemoria, appuntamenti,
documenti) solo sugli schermi personali di chi parla e mai nella zona grigia del
riconoscimento. La stanza oggi è `schermi_stanza` (vuoto = tutti); domani la darà il
satellite (`Mittente.stanza`). Nel registro dei turni ogni tool con schede ha `schede`
(tipo, visibilità, quanti schermi, motivo); i rifiuti per visibilità sono regole di permesso
(`schermo_personale`, `schermo_ospite`, `schermo_zona_grigia`).

Gli **agenti** (02/10/2026, «gemma davanti, agenti dietro»,
[`ricerche/2026-10-02-llm-per-spark.md`](ricerche/2026-10-02-llm-per-spark.md)). I tre tool ci
sono solo con un agente configurato: `dgx.yaml` accanto a `calliope.yaml` (la DGX via tunnel
SSH, o «diretto» in LAN) oppure `agenti_url`. Il front-end (gemma4) decide se delegare: il
criterio sta nella descrizione e nel prompt (il risultato è un programma o un file complesso;
le domande brevi di programmazione e le spiegazioni restano alla voce), non in una regola. Il
lavoro lo fa `calliope/agenti/ciclo.py`, un ciclo scritto in proprio sull'API nativa di
Ollama: per il **codice** sei strumenti su una **sandbox** (`elenca_file`, `leggi_file`,
`scrivi_file`, `esegui_python`, `esegui_test`, `consegna`: niente shell, niente rete, niente
file fuori dalla cartella del lavoro; i test li rifà il programma alla fine), per i
**documenti** lo scrittore di `calliope/documenti/` con il modello grande (bozza con il
ragionamento, poi il JSON con lo schema), per i **modelli di documento** lo schema dei campi
riempito dal modello e compilato dal codice (dati mancanti → domanda, mai inventati), per le
**ricerche** `biblioteca_cerca` e una relazione in Word. Tetti di passi, token e minuti. La
voce non aspetta mai: i tool leggono lo stato in memoria, il collegamento (tunnel, Ollama
remoto) lo fa il thread dei lavori. A lavoro finito: file in Documenti\Calliope\Lavori,
scheda personale `lavoro` (il codice intero, sullo schermo) e un annuncio breve con il
segnale acustico, mai il codice a voce. Con l'agente sullo stesso Ollama della voce l'arbitro
(`arbitro.py`) chiude lo stream dell'agente appena qualcuno parla a Calliope e lo fa ripartire
dopo la risposta.

I **minori** (05/10, [`ricerche/2026-10-05-minori.md`](ricerche/2026-10-05-minori.md)): dopo il
livello `ToolRegistry.call` chiede a `minori.permesso` se il preset della fascia di chi parla
permette il tool (internet, agenti, PC, documenti, ufficio, estensioni `est_<nome>`), con una
frase pronta e una regola `minore_*`. `casa_comando` filtra le entità per fascia
(`minori.casa_consentita`), `web_cerca` usa il SafeSearch della fascia, `calcola` non dà il
risultato con un esercizio aperto. Il preset arriva al modello nei dati del turno; il guardiano
filtra le frasi in `main.py`, non nei tool.

Il **saluto** («Ciao Dario») resta in Python: è deterministico e non costa un turno LLM.

## 8. MCP (dopo)

Il confine MCP serve per **ampliare**: biblioteca Kiwix, musica, file sui PC, web. Home
Assistant è diventato nativo il 01/10/2026 (`calliope/casa/`): la sua API WebSocket ha la
verifica a secco dei comandi, che serve alle regole di sicurezza, e niente SDK MCP. Un ponte JSON-RPC (la specifica 2026-07-28 è senza stato) evita l'SDK e
il blocco `cryptography`. Allowlist per server e per livello.

## 9. Rischi e conferme

- `lettura` — nessuna conferma.
- `azione` — esegue, poi racconta.
- `sensibile` — chiede conferma (in futuro un secondo fattore, vedi visione).

## 10. Roadmap

1. **Oggi**: registro, ciclo di tool calling, tool di identità/voce/ora.
2. **Da discutere**: memoria (SQLite contro altre strade).
3. **Dopo**: ponte MCP. Agenti in secondo piano e arbitro: fatti il 02/10 (`calliope/agenti/`);
   restano llama-server per l'agente, le domande dell'agente a metà lavoro
   (`lavori_rispondi`), i modelli `.docx` con docxtpl e le presentazioni in `.pptx`.
