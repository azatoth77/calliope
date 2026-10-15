# Calliope — architettura dei tool

*Proposta del 23 settembre 2026. Fonti: [`docs/visione.md`](visione.md) (principi 5, 6, 9) e
[`ricerche/2026-09-21-orchestrazione-agenti.md`](ricerche/2026-09-21-orchestrazione-agenti.md).
Tenuto allineato al codice: tabella dei tool, `ToolSpec` e albero dei file rivisti il 14/10 sul
registro vero (`build_registry` in `tools/builtin.py` e ciò che `main.py` registra a parte): 86 tool
in un registro con tutto acceso, più un `est_<nome>` per estensione attiva. In un'installazione con
tutti i servizi il modello vede **75 schemi** uguali per ogni livello; si aggiungono `meteo_leggi`
(entità meteo in Home Assistant), `immagine_guarda` (`immagini_storia: descrizione`), i quattro tool
dei minori (un minore in casa), `stanza_pausa` e `stanza_cerca` (stanza accesa), `conoscenti` e
`conoscente_livello` (`stanza_conoscenti`); `argomento` prende il posto di `conversazione_nuova` con
`eventi: attivo`. Nomi nuovi dall'08/10, i vecchi validi in `registry.NOMI_VECCHI`.
(Storico: «72 schemi» il 09/10, «78» fino al 13/10.)*

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

Struttura del package dal 26/09/2026 (roadmap 2), solo i moduli che riguardano i tool; l'elenco
completo per stadio è nella tabella di `CLAUDE.md`:

```
calliope/                 # package: python -m calliope
├── main.py               # ciclo principale
├── config.py             # Config, load_config (calliope.yaml), VOICE_MAP, costanti
├── brain.py              # ciclo di tool calling in streaming
├── tools/
│   ├── spec.py           # ToolSpec, ToolContext
│   ├── registry.py       # filtro per livello, esecuzione, NOMI_VECCHI, nome storpiato
│   ├── dialogo.py        # argomenti controllati sullo schema, errori in parole (09/10)
│   ├── builtin.py        # i tool nativi di Calliope e build_registry
│   ├── proposta.py       # proposta_rispondi (10/10, stato del dialogo)
│   ├── argomento.py      # argomento (10/10, solo con `eventi: attivo`)
│   ├── pc.py             # i tool pc_* (PC a voce)
│   ├── documenti.py      # documento_crea, documento_modifica, documento_leggi
│   ├── casa.py           # casa_comando, casa_stato, casa_integrazione, citta_casa_salva, meteo_leggi
│   ├── schermi.py        # schermo_mostra, schermo_gestisci, schede_pulisci, gioco_comando (11/10)
│   ├── agenti.py         # lavoro_affida, lavoro_stato, lavoro_annulla, lavoro_rispondi, lavoro_risultato, programma_esegui
│   ├── sviluppo.py       # sviluppo_apri, sviluppo_passo, sviluppo_collauda, sviluppo_chiedi, sviluppo_correggi (modalità sviluppo, 08/10)
│   ├── estensioni.py     # estensione_gestisci e i tool est_<nome> delle estensioni attive
│   ├── conversazioni.py  # conversazione_cerca (anche cronologica, 08/10), conversazioni_dimentica, conversazione_nuova (09/10)
│   ├── conserva.py       # dati_conservati: consenso alla voce, revoca, stato, svuota (12/10)
│   ├── stanza.py         # stanza_pausa: ospiti, pausa, riprendi, stato (13/10, solo con la stanza accesa); stanza_cerca (14/10, passo 4, con `stanza_cerca`)
│   ├── conoscenti.py     # conoscenti (elenco, dimentica) e conoscente_livello (promuovi, declassa): 14/10, decisione 0030, con `stanza_conoscenti`
│   ├── web.py            # web_cerca (SearXNG)
│   ├── notizie.py        # notizie (feed RSS scaricati in casa, 13/10)
│   ├── immagini.py, allegati.py  # immagine_guarda, immagine_archivia, pc_guarda; allegato_leggi, allegato_archivia, cassetto_gestisci
│   ├── archivio.py, ufficio.py   # archivio_cerca/scadenze/somma; modello_compila, anagrafica_cerca/salva
│   ├── minori.py, esercizi.py    # richiesta_tutore, compiti_aiuto, minore_gestisci; esercizi (08/10)
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
├── politica.py           # politica unica dei tool: CLASSI, conferme, sfide (05/10); valore.py, provenienza.py
├── stato_dialogo.py      # macchina a stati del dialogo, in ombra (10/10)
├── eventi/               # registro degli eventi per persona (10/10, decisione 0027)
├── stanza/               # conversazione di stanza (13–14/10, decisione 0029): ascolto, registro,
│                         # contesto, cerca, eco, tenuta, guardia, conoscenti (0030)
├── notizie/              # feed RSS scaricati in casa (13/10)
├── web/                  # SearXNG (web_cerca) e il suo aggiornamento (motore.py)
├── estensioni/           # estensioni permanenti, guardrail, motore dei giochi
├── archivio/, ufficio/   # documenti di casa (grafo); modelli, rubrica, fatture
├── esercizi/             # esercizi generati da Calliope e programma ministeriale
├── satellite/            # satelliti (WebSocket, TLS, inoltro)
├── conserva.py           # dati conservati per le misure (12/10)
├── minori.py, guardiano.py, avvisi_audio.py  # minori, guardiano, audio degli avvisi (14/10)
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
    riservato: bool           # argomenti e risultato fuori dal registro (archivio di casa)
    non_fidato: bool          # il risultato è testo esterno (web_cerca)
    resta_in_storia: bool     # ...ma resta nella storia in busta (notizie, 13/10)
    classe, fonte, chiave     # politica unica (05/10): classe del tool, fonte del dato, argomenti chiave
    prepara: Callable | None  # conversione di forma degli argomenti prima dei permessi (08/10)
    nomi: dict                # argomenti che nominano qualcosa → tipo (08/10, argomenti_incerti.py)
```

`nomi` (08/10) dice quali argomenti nominano un luogo, un dispositivo di casa, un'estensione,
un contatto, una persona, un file o un valore: su questi si misura quanto Whisper era sicuro
delle parole e, dopo un esito vuoto, il modello riceve «forse intendeva…»
([stt-tts](aree/stt-tts.md)).

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
  risultato da leggere. Un nome di prima dell'08/10 (`NOMI_VECCHI`: `delega_lavoro`,
  `lavori_stato`, `estensione_crea`, `estensioni_gestisci`, `sviluppo`, `sviluppo_prova`…)
  vale come il nome nuovo, con tutti i controlli (regola `tool_nome_vecchio`); un nome
  storpiato dal modello entro due lettere vale il tool vicino (regola `tool_nome_corretto`).
- Senza rete (`online=False`) i tool con `requires_internet=True` **spariscono
  dall'elenco** (principio 5) e il resto continua a funzionare.

## 5. Livelli e permessi

Principio 9 della visione: ospite → familiare → chi amministra.

| Livello | Quando | Vede |
|---|---|---|
| `ospite` | voce non riconosciuta (default) | sola lettura |
| `familiare` | voce riconosciuta | voce, azioni a basso rischio |
| `amministra` | `Primo`/`Prima` (il primo utente) | tutto |

Dal 14/10 (decisione [0030](decisioni/0030-conoscenti.md)) c'è un **tipo** di profilo in più,
non un livello: il **conoscente**, una voce di fuori casa salvata da chi amministra (nome, cognome,
nota, impronta) in `conoscenti.json`, **fuori** da `speakers.json`. Nessun percorso dei comandi lo
riconosce: a ogni effetto è un **ospite**; solo le righe della stanza hanno il suo nome, e la
conservazione (categoria `conoscente`) tiene e cerca solo quelle. Diventa familiare solo con
`conoscente_livello` detto da chi amministra.

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
6. Dal 09/10 gli argomenti si controllano contro lo schema prima della chiamata e un errore
   torna al modello in parole, con esempio e `cosa_fare` (`calliope/tools/dialogo.py`); dopo
   un errore correggibile il modello richiama invece di dire «riprovo» (giro di correzione,
   [`ricerche/2026-10-09-dialogo-tool.md`](ricerche/2026-10-09-dialogo-tool.md)).

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

## 7. Tool nativi

«Classe» è la classe della politica unica (`politica.CLASSI`, o `ToolSpec.classe` per i tool
registrati a runtime); «C'è» dice quando il tool è nel registro.

| Tool | Livello | Rischio | Classe | C'è | Cosa |
|---|---|---|---|---|---|
| `chi_parla` | ospite | lettura | sicuro | sempre | chi parla adesso (nome, se riconosciuto; dal 07/10 età e compleanno dal profilo) |
| `elenca_voci` | ospite | lettura | sicuro | sempre | le voci TTS disponibili |
| `ora_attuale` | ospite | lettura | sicuro | sempre | ora locale |
| `data_oggi` | ospite | lettura | sicuro | sempre | data locale |
| `calcola` | ospite | lettura | sicuro | sempre | conti esatti su un'espressione (valutatore `ast`), con `da_dire` per la voce |
| `data_calcola` | ospite | lettura | sicuro | sempre | conti con le date, esatti (05/10): età (anche di una persona di casa, dalla data di nascita del profilo), giorni che mancano o passati, giorno della settimana, distanza tra due date; `calcola` rimanda qui le date; `da_dire` per la voce |
| `biblioteca_cerca` | ospite | lettura | sicuro | con i file ZIM | fatti precisi da Wikipedia offline (`biblioteca.py`); registrato solo se ci sono i file ZIM. Con Wikiquote scaricata e indicizzata (01/10) anche citazioni e «chi ha detto…?», e la descrizione lo dice (`biblioteca_spec(citazioni=True)`) |
| `timer_imposta` | ospite | azione | azione | sempre | timer della casa; durata come detta a voce (`tempi.py`) |
| `promemoria_imposta` | familiare | azione | azione | sempre | promemoria personale; orario come detto a voce |
| `appuntamento_aggiungi` | familiare | azione | azione | sempre | appuntamento personale, con un avviso automatico `appuntamento_anticipo_min` prima (60) se c'è ancora tempo |
| `appuntamenti_elenca` | familiare | lettura | sicuro | sempre | appuntamenti di un giorno o intervallo detto a voce (`tempi.parse_day_range`); vuoto = 7 giorni |
| `agenda_elenca` | ospite | lettura | sicuro | sempre | timer attivi, promemoria di chi parla e appuntamenti dei prossimi 2 giorni |
| `agenda_annulla` | ospite | azione | azione | sempre | annulla un timer, un promemoria o un appuntamento (con il suo avviso) per descrizione |
| `elenca_utenti` | familiare | lettura | sicuro | sempre | persone della casa registrate (non la rubrica): impronta della voce sì/no, minorenne, età e compleanno a sé, ai tutori e a chi amministra (07/10) |
| `cambia_voce` | familiare | azione | azione | sempre | cambia la voce di chi parla |
| `rinomina_interlocutore` | familiare | azione | pericoloso | sempre | rinomina chi parla (prima propone, cambia al «sì»); un ruolo o una parentela come nome («Amministratore», «La Mamma», «Ospite») non si propone nemmeno (15/10, regola `rinomina_ruolo`) |
| `registra_utente` | amministra (dal 05/10, con la frase di sfida) | azione | pericoloso | sempre | avvia l'arruolamento di una persona nuova con la data di nascita (o «maggiorenne») e i tutori; un minore ha il preset della sua fascia (`calliope/minori.py`) |
| `compiti_aiuto` | familiare (solo con un minore in casa; agisce per i minori con i compiti guidati) | lettura | sicuro | un minore in casa | registra l'esercizio, controlla la risposta con il valutatore di `calcola`, mai la soluzione prima di 5 errori, poi l'avviso ai tutori |
| `esercizi` | familiare (solo con un minore in casa; il codice: i minori per sé, i loro tutori e chi amministra, mai gli ospiti) | lettura | sicuro | un minore in casa | esercizi generati da Calliope (08/10, `calliope/esercizi/`): inizia, rispondi (corregge il codice), aiuto, salta, ripeti, segnala, soluzione, fine, argomenti, riepilogo. Dal 12/10 `materia` con i valori ammessi (matematica, italiano, logica, fisica, chimica) e `argomento` con la descrizione «con le sue parole»; risposte con l'unità di misura lette nel codice (`calliope/unita.py`); con una sessione aperta e l'azione omessa: «rispondi» se c'è la risposta, «ripeti» se l'argomento è lo stesso (regola `esercizi_azione_dedotta`) |
| `minore_gestisci` | familiare (il codice: un tutore o chi amministra, dalla voce) | azione | pericoloso | un minore in casa | preset di un minore: stato, imposta, orari, estensioni, autorizzazione a tempo, nascita, tutori, riepilogo dei compiti; dal 14/10 `avvisi` («cos'era quell'avviso?»: gli avvisi di pericolo consegnati a chi parla, con data e origine) |
| `ricorda` | familiare | azione | azione | sempre | salva un fatto su chi parla (memoria persistente, `memory.py`); con `per_tutti` è un fatto della casa (persona `casa`), visto da tutti i familiari |
| `dimentica` | familiare | azione | azione | sempre | toglie un fatto (o «tutto»): prima tra quelli di chi parla, poi tra quelli della casa |
| `lista_aggiungi` | familiare | azione | azione | sempre | aggiunge voci a una lista della casa (`liste.py`), senza doppioni; si annota chi le ha aggiunte |
| `lista_leggi` | familiare | lettura | sicuro | sempre | legge una lista con il conteggio (le prime 8 e «e altre N») |
| `lista_togli` | familiare | azione | azione | sempre | toglie voci con confronto tollerante; «tutto» svuota la lista |
| `pc_stato` | familiare | lettura | sicuro | con un PC che ha quella capacità (`load_pc`) | volume, musica, luminosità, batteria, bloccato; `programmi_aperti` solo proprietario o chi amministra |
| `pc_volume` | familiare (ospite se `pc_ospite_volume_media`) | azione | pericoloso | con un PC che ha quella capacità (`load_pc`) | alza, abbassa, imposta, muto, riattiva; valori come detti («un po'» = `pc_passo`), tra 0 e 100 |
| `pc_media` | familiare (ospite se `pc_ospite_volume_media`) | azione | pericoloso | con un PC che ha quella capacità (`load_pc`) | riproduci, pausa, avanti, indietro sulla sessione multimediale di Windows |
| `pc_luminosita` | familiare | azione | pericoloso | con un PC che ha quella capacità (`load_pc`) | alza, abbassa, imposta la luminosità dello schermo |
| `pc_apri_app` | familiare | azione | pericoloso | con un PC che ha quella capacità (`load_pc`) | apre un'app del catalogo `pc_app` (enum); mai un comando dal modello |
| `pc_blocca` | familiare | azione | pericoloso | con un PC che ha quella capacità (`load_pc`) | blocca lo schermo |
| `pc_cerca_file` | proprietario o chi amministra | lettura | sicuro | con un PC che ha quella capacità (`load_pc`) | Windows Search sulla cartella dell'utente; periodo detto a voce (`tempi.parse_past_range`) |
| `pc_apri_file` | proprietario o chi amministra | azione | pericoloso | con un PC che ha quella capacità (`load_pc`) | apre il risultato n dell'ultima ricerca della stessa persona (15 minuti); anche chi non è proprietario, se è un documento appena fatto preparare da lui |
| `documento_crea` | familiare | azione | azione | con almeno una libreria dei documenti | documento Word, Excel o PDF nuovo; il modello passa formato e richiesta come detta, il testo lo scrive una seconda richiesta a Ollama (`calliope/documenti/`) |
| `documento_modifica` | familiare | azione | azione | con almeno una libreria dei documenti | cambia l'ultimo documento di chi parla («cambia la data in 15 ottobre», «aggiungi una riga: internet 30»); il file si riscrive con lo stesso nome |
| `documento_leggi` | familiare | lettura | sicuro | con almeno una libreria dei documenti | che cosa c'è in un documento preparato da Calliope per chi parla, anche rimasto sul server («cosa c'è in quel file?», «riassumimelo», «aprilo»: sulla scheda con «Scarica»); mai un altro documento al posto di quello detto (09/10) |
| `casa_comando` | familiare (ospite per i domini di `casa_ospite_domini`) | azione | pericoloso | `casa_enabled` con indirizzo e token | un comando per la casa in una frase breve nella forma di Home Assistant («accendi la luce della cucina»); verifica a secco, regole di Calliope, poi l'agente integrato di HA; la sua risposta è la `risposta_finale` |
| `casa_stato` | familiare (ospite come sopra) | lettura | sicuro | `casa_enabled` con indirizzo e token | com'è la casa dagli stati delle entità esposte, senza richieste a HA: «temperatura in camera», «cosa c'è acceso», «porta del garage» |
| `casa_integrazione` | familiare | lettura | sicuro | `casa_enabled` | a che punto è il collegamento con HA e il prossimo passo (dettagli solo a chi amministra); con `per_iscritto` la guida in PDF o Word, da un testo fisso |
| `citta_casa_salva` | ospite | azione | azione | sempre | la città della casa detta a voce (09/10, `calliope/luogo.py`), per il meteo e ciò che dipende dal luogo; `conferma` solo dopo il «sì» alla domanda «vuoi che mi ricordi…» |
| `meteo_leggi` | ospite | lettura | sicuro | un'entità meteo esposta in Home Assistant | il meteo di casa da Home Assistant (09/10): cielo, temperatura, vento e previsioni per `quando` detto a voce; non per la temperatura delle stanze (`casa_stato`) |
| `calliope_stato` | ospite | lettura | sicuro | sempre | «cosa sai fare?», «cosa manca?», «perché non va…?» dal registro delle capacità: chi amministra sente motivo e prossimo passo, i familiari cosa funziona, gli ospiti cosa possono chiedere; dal 09/10 «cosa sai fare?» per grandi aree (`area` per il dettaglio), `cosa=novita` (con `periodo`) dal CHANGELOG della versione installata, `cosa=chi_sei` con fatti veri; `risposta_finale` |
| `installa_proponi` | familiare (il codice accetta solo chi amministra, riconosciuto dalla voce nel turno) | lettura | sicuro | con il servizio delle installazioni | proposta di un'azione del catalogo (enum): dimensione, spazio libero, tempo, internet, domanda finale; prerequisiti controllati; non scarica niente |
| `installa_avvia` | amministra | sensibile | pericoloso | con il servizio delle installazioni | avvia l'azione proposta nel turno **prima** alla stessa persona; senza offerta valida rifiuta |
| `installa_gestisci` | familiare (annullare solo chi amministra) | azione | pericoloso | con il servizio delle installazioni | «a che punto è?», «annulla il download» |
| `proposta_rispondi` | ospite | lettura | sicuro | sempre (fuori dagli schemi con `dialogo_interprete: spento`) | la risposta a una proposta aperta dello «Stato del dialogo» (10/10, `calliope/stato_dialogo.py`): `esito` si, no, correzione, rinvio, altro; il «sì» lo esegue il sistema con gli argomenti già proposti; fuori dalla storia a turno finito |
| `schermo_mostra` | ospite (il codice decide cosa può vedere) | lettura | sicuro | con il server degli schermi | «mostramelo sullo schermo», «metti la lista sullo schermo», «fammelo leggere», «togli dallo schermo»: `cosa` in enum (ultima, risposta, lista, timer, promemoria, documento, casa, niente); la scheda la costruisce il codice, la frase dice cosa è successo davvero (`risposta_finale`) |
| `schermo_gestisci` | amministra | azione | pericoloso | con il server degli schermi | abbina (codice di 6 cifre, stanza, personale), scollega, elenca gli schermi; il codice è un argomento segreto (`ToolSpec.segreti`) |
| `schede_pulisci` | familiare (il codice vuole la voce riconosciuta: mai la zona grigia) | azione | azione | con il server degli schermi | «pulisci le mie schede» (08/10): la cronologia delle schede di chi parla, su disco e sui suoi schermi personali; solo le sue, senza conferma (documenti, lavori e file restano); lo sviluppo aperto resta. Anche il tasto «Pulisci» della pagina (`POST /api/schede`) |
| `gioco_comando` | ospite | lettura | sicuro | estensioni, schermi e `giochi_enabled`, e dal 14/10 sera solo con `giochi_giudice: false` (con il giudice di fase acceso la stessa cosa la fa il giudice, `calliope/gioco_giudice.py`) | un comando a voce del gioco sullo schermo detto con altre parole (11/10 sera, «apri la terza» → tre): `comando` solo tra quelli che il gioco dichiara nel contesto del turno |
| `stanza_pausa` | ospite (`ospiti`, `pausa`, `stato`: spengono o leggono); `riprendi` solo un adulto riconosciuto dalla voce (non zona grigia, non un minore, non scritto) | azione (classe «sicuro», effetto E1) | sicuro | `stanza: ombra` | l'ascolto della conversazione della stanza sul satellite da cui si parla (13/10, passo 1, `calliope/stanza/`): «abbiamo ospiti» lo ferma per `stanza_ospiti_ore` (4 h), «smetti di ascoltare la stanza» per i minuti detti o `stanza_pausa_min`, «ascolta di nuovo la stanza». Si registra solo con `stanza: ombra` (main.py) |
| `stanza_cerca` | familiare (il codice vuole una persona di casa riconosciuta, dalla voce o dal suo schermo personale: mai la zona grigia) | lettura (classe «sicuro» con la fonte `stanza`; non fidato e riservato) | sicuro | `stanza: ombra` e `stanza_cerca` | ciò che si è detto vicino ai satelliti e il blocco caldo non ha più (14/10, passo 4, `calliope/stanza/cerca.py`): «di cosa parlavamo in cucina prima?», «cosa aveva detto Carlo della gita?». Argomenti facoltativi `parole`, `persona`, `stanza`, `quando`, `dalle`/`alle`. Un adulto vede le stanze dove era presente (e gli ultimi minuti di quella da cui parla), le parole di un minore solo i suoi tutori, un minore solo le sue, le voci non riconosciute mai; in pausa per ospiti non cerca. Le righe ancora in coda si aspettano al più `stanza_cerca_attesa_max_s`, con la frase `attesa.stanza` oltre `stanza_cerca_attesa_s`. Risultato in busta, fuori dalla storia a risposta finita, mai nel registro. Rete `spinta_stanza`: un «non lo so» senza tool fa cercare Brain con la frase. Si registra solo con la stanza accesa e `stanza_cerca: true` |
| `conoscenti` | amministra (il codice vuole la voce sopra soglia o il «sì» breve compatibile; mai lo scritto né la zona grigia) | azione (`elenco` lettura; `dimentica` distruttiva, effetto E3) | azione | `stanza: ombra` e `stanza_conoscenti` | i conoscenti (14/10, decisione 0030, `calliope/stanza/conoscenti.py`): `elenco` («chi conosci?», con le voci nuove che aspettano una risposta sullo schermo), `dimentica` («dimentica Marco»: impronta, profilo e righe della stanza su disco, dopo la domanda e il «sì»; con più omonimi chiede quale dicendo cognome e nota). Si registra solo con la stanza accesa e `stanza_conoscenti: true` |
| `conoscente_livello` | amministra (come sopra) | pericoloso (chiesto nel turno, sfida con dati di mezzo, effetto E4) | pericoloso | `stanza: ombra` e `stanza_conoscenti` | chi è di famiglia (14/10, decisione 0030): `promuovi` un conoscente a familiare (stesso id e impronta, in `speakers.json` con i permessi dei familiari; un minore vuole `nascita` e `tutori` adulti; poi la proposta di rifare la voce), `declassa` un familiare a conoscente (mai chi amministra né un minore, mai chi parla), con la domanda e il «sì». Stessa registrazione di `conoscenti` |
| `dati_conservati` | familiare (consenso e revoca della propria voce; `svuota` solo chi amministra, con la voce) | azione (`stato` lettura) | azione | sempre | i dati tenuti 60 giorni per le misure (12/10, `calliope/conserva.py`): `consenso_voce` con la voce sopra soglia, la domanda e il «sì» (mai scritto né zona grigia né un minore), `revoca_voce` subito con le registrazioni cancellate, `stato` (cosa tengo di te), `svuota` di tutti o di una persona con la domanda. Si registra con la conservazione (`build_registry(conserva=True)`) |
| `lavoro_affida` | familiare | azione | pericoloso | con un agente (`dgx.yaml` o `agenti_url`) | affida a un agente in secondo piano un lavoro lungo il cui risultato è un file complesso: `tipo` documento (anche da un `modello`), ricerca, altro; `compito` con i dati detti. Dal 08/10 senza il codice: un tipo codice passa da sé a `sviluppo_apri` (regola `lavoro_codice_sviluppo`). I lavori costosi chiudono con «Procedo?» e partono solo con `proposta` = l'id, nella risposta dopo, della stessa persona; `risposta_finale` (fino al 08/10 `delega_lavoro`) |
| `lavoro_stato` | familiare | lettura | sicuro | con un agente (`dgx.yaml` o `agenti_url`) | a che punto sono i lavori (passo dell'agente, coda, una tappa, ultimo finito) (era `lavori_stato`) |
| `lavoro_annulla` | familiare (gli altrui solo chi amministra) | azione | azione | con un agente (`dgx.yaml` o `agenti_url`) | ferma il lavoro in corso, in coda o fermo a una tappa, subito (stream chiuso, sandbox fermata) (era `lavori_annulla`) |
| `lavoro_rispondi` | familiare | azione | azione | con un agente (`dgx.yaml` o `agenti_url`) | la risposta a una domanda dell'agente a metà lavoro; a una tappa vale «continua» (era `lavori_rispondi`) |
| `lavoro_risultato` | familiare | lettura, risultato non fidato | sicuro | con un agente (`dgx.yaml` o `agenti_url`) | il risultato di un lavoro finito: riassunto, più dettaglio, sullo schermo, PDF o Word (era `risultato_lavoro`) |
| `programma_esegui` | familiare (chi l'ha chiesto o chi amministra) | azione | pericoloso | con un agente (`dgx.yaml` o `agenti_url`) | esegue di nuovo il programma di un lavoro di codice finito (era `lavori_esegui`) |
| `sviluppo_apri` | familiare (il codice e le estensioni: solo chi amministra, dalla voce; un gioco anche un familiare adulto) | azione | pericoloso | con un agente (`dgx.yaml` o `agenti_url`) | apre uno sviluppo (08/10, versione 2): `tipo` estensione (anche `modifica` di una che c'è, `gioco`) o programma (anche su un `file` del PC o un `allegato`); proposta «Entriamo in modalità sviluppo per «…». Ho capito così: … Va bene così, o la cambiamo?»; dal 11/10 con ciò che oggi non si può fare e, per una richiesta ricca, la proposta delle tappe («Comincio dalla prima tappa, o lo faccio tutto insieme?», `tappe` = false per tutto insieme); il «sì» con `proposta` = l'id (fino al 08/10 `estensione_crea` e `delega_lavoro` di codice) |
| `sviluppo_passo` | familiare (il codice: solo chi amministra) | azione | pericoloso | con un agente (`dgx.yaml` o `agenti_url`) | la modalità sviluppo (`calliope/sviluppo.py`): stato, avanti (anche «continua» a una tappa), analisi (con `cambia`), rifai (dopo un lavoro fermato o non andato riparte subito con la stessa specifica, 08/10 sera), ferma (il lavoro dell'agente si ferma subito, 08/10 sera), sospendi (una pausa: il lavoro in corso finisce), riprendi (`quale`), chiudi (con la conferma), promuovi, completa (dopo la consegna l'agente fa quello che manca rispetto alla richiesta, o la tappa dopo; alla revisione con qualcosa che manca anche «continua», 11/10); le fasi le cambia il codice (era `sviluppo`) |
| `sviluppo_collauda` | familiare (il codice: solo chi amministra) | azione, risultato non fidato | pericoloso | con un agente (`dgx.yaml` o `agenti_url`) | il collaudo: la versione candidata dell'estensione provata prima dell'approvazione nel suo container, o il programma eseguito di nuovo; `argomenti` per un'estensione con più input, più valori detti insieme = un collaudo per valore (08/10 sera); un collaudo che non va → «Lo faccio correggere?» (era `sviluppo_prova`) |
| `sviluppo_chiedi` | familiare (il codice: solo chi amministra) | lettura, risultato non fidato | sicuro | con un agente (`dgx.yaml` o `agenti_url`) | la domanda a chi ha scritto il codice (08/10): una passata del modello dell'agente in sola lettura con il contesto dello sviluppo conservato (specifica, collaudi, diario, file, fonti), entro `sviluppo_chiedi_s` |
| `sviluppo_correggi` | familiare (il codice: solo chi amministra) | azione | pericoloso | con un agente (`dgx.yaml` o `agenti_url`) | la correzione come passo a sé (08/10): un lavoro sui file della versione provata, con i collaudi che non vanno e la diagnosi di `sviluppo_chiedi`, la specifica resta; a una tappa «cambia e continua» |
| `estensione_gestisci` | familiare (il codice: approvare, consentire e gestire solo chi amministra) | azione | pericoloso | con le estensioni | le estensioni attive o no: elenca, approva una versione nuova, rifiuta, disattiva, riattiva, indietro, revoca, rimuovi, rinomina (08/10, solo il titolo, senza agente), consenti o nega un'azione chiesta da un'estensione; per usarne una il modello chiama il suo `est_<nome>` (era `estensioni_gestisci`) |
| `est_<nome>` | dal manifesto dell'estensione | lettura o azione | dal manifesto: azione se agisce, altrimenti sicuro (una lettura che manda fuori gli argomenti resta sicura ma «esce») | estensione attiva e approvata (al più `estensioni_max_attive`) | un tool per ogni estensione attiva (04/10): schema dal manifesto, risultato non fidato (fonte «estensione»); un gioco con la scheda apre la partita sullo schermo |
| `conversazione_cerca` | familiare | lettura | sicuro | `conversazioni_enabled` (archivio) | ciò che ci siamo detti nelle conversazioni passate di chi parla (archivio di 30 giorni, ricerca ibrida); con `cronologico` (08/10) le ultime conversazioni in ordine di tempo, «più indietro» continua; `ospiti` solo per chi amministra |
| `conversazione_nuova` | ospite | azione (classe sicura) | sicuro | sempre (con `eventi: attivo` al suo posto `argomento`) | chiude la conversazione di adesso e ne comincia una nuova quando la persona lo chiede con parole sue (09/10); `cosa` con la cosa nominata («il collaudo») non fa niente; la regola breve «ricominciamo» resta |
| `argomento` | ospite | lettura | sicuro | registrato sempre, negli schemi solo con `eventi: attivo` | il cambio d'argomento (10/10, § 13 del registro degli eventi): `nuovo` con un titolo o `riprendi` un argomento messo da parte; ciò che era aperto va da parte, non si chiude. Negli schemi al posto di `conversazione_nuova` solo con `eventi: attivo` |
| `conversazioni_dimentica` | familiare | azione | pericoloso | `conversazioni_enabled` (archivio) | cancella dall'archivio le conversazioni di chi parla, dopo la conferma (i ricordi restano) |
| `web_cerca` | da `web_livello` (predefinito familiare) | lettura, risultato non fidato | sicuro | SearXNG configurato e pronto (compare anche dopo l'avvio) | ciò che cambia nel tempo (meteo, orari, prezzi; le notizie solo senza il tool `notizie`) da SearXNG; nomi delle persone tolti dalla domanda |
| `notizie` | da `notizie_livello` (predefinito ospite) | lettura, risultato non fidato che resta nella storia in busta | sicuro | `notizie_enabled` (di serie sì) e la rete | le notizie dai feed RSS scaricati in casa (13/10): fatti numerati, «dimmi di più» con `fatto`; minori solo sport, tecnologia e ragazzi; SearXNG come ripiego |
| `immagine_guarda`, `immagine_archivia` | familiare | lettura; azione | sicuro; azione | foto accese, modello che vede, `immagini_storia: descrizione`; foto accese e l'archivio | rivedere una foto della conversazione; archiviarla tra i documenti di casa solo se chiesto |
| `pc_guarda` | familiare | sensibile | azione | foto accese e un PC con schermata o webcam | una foto nuova dalla webcam o una schermata, su richiesta |
| `allegato_leggi`, `allegato_archivia` | familiare | lettura; azione | sicuro; azione | `allegati_enabled` con gli schermi; con gli allegati e l'archivio | una parte di un file allegato (anche dal cassetto dei giorni passati, 08/10); archiviarlo solo se chiesto |
| `cassetto_gestisci` | familiare (`di`: solo un tutore per i file del ragazzo) | azione | azione | con gli allegati e il cassetto | il cassetto dei file della persona (7 giorni, 08/10): tieni tra i documenti, elimina, ancora una settimana |
| `archivio_cerca`, `archivio_scadenze`, `archivio_somma` | familiare | lettura (riservati) | sicuro | con l'archivio dei documenti di casa | i documenti di casa archiviati: un dato, cosa scade, quanto si è speso (la somma la fa il programma) |
| `modello_compila`, `anagrafica_cerca`, `anagrafica_salva` | familiare | azione; lettura; azione | azione; sicuro; azione | con i modelli dell'ufficio | ufficio: fattura (anche XML), nota di credito, preventivo, DDT e modelli dell'utente; la rubrica dei clienti e fornitori, con la proposta e il sì |
| `richiesta_tutore` | familiare (solo con un minore in casa) | azione | azione | un minore in casa | il minore chiede al tutore un gioco, un'estensione, l'agente, più tempo di gioco o di restare sveglio |

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
[`ricerche/2026-10-02-llm-per-spark.md`](ricerche/2026-10-02-llm-per-spark.md)). I tre tool
*[storico: dall'08/10 sono i cinque `lavoro_*` e `programma_esegui` della tabella, e il codice passa
dalla modalità sviluppo; dettagli in [agenti-estensioni](aree/agenti-estensioni.md)]* ci
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

*Storico (23/09): dal 05/10 conferme e sfide non le decide `risk` ma la **classe** della politica
unica (`calliope/politica.py`: sicuro, azione, pericoloso, vietato; colonna «Classe» della tabella
del § 7), con la provenienza degli argomenti e, dal 09/10, la politica per valore
(`politica_per_valore`); `risk` resta nel `ToolSpec` (Brain lo usa per sapere se un tool agisce).
Dettagli in [sicurezza-politica](aree/sicurezza-politica.md).*

## 10. Roadmap

*Storica (23/09); la roadmap di oggi è in [`roadmap.md`](roadmap.md). Fatti: memoria SQLite
(26/09), agenti e arbitro (02/10), domande a metà lavoro (`lavoro_rispondi`, 03/10), docxtpl e
python-pptx (03/10), l'agente su vLLM invece di llama-server (02/10); resta il ponte MCP.*

1. **Oggi**: registro, ciclo di tool calling, tool di identità/voce/ora.
2. **Da discutere**: memoria (SQLite contro altre strade).
3. **Dopo**: ponte MCP. Agenti in secondo piano e arbitro: fatti il 02/10 (`calliope/agenti/`);
   restano llama-server per l'agente, le domande dell'agente a metà lavoro
   (`lavoro_rispondi`), i modelli `.docx` con docxtpl e le presentazioni in `.pptx`.
