# Casa (Home Assistant)

*Comandi e letture della casa via Home Assistant, regole, errori di HA in italiano. Documento d'area: nato il 06/10/2026 dividendo CLAUDE.md (proposta P7 di [`../ricerche/2026-10-06-analisi-complessiva.md`](../ricerche/2026-10-06-analisi-complessiva.md)). Chi lavora su quest'area aggiorna questo file; in CLAUDE.md al più una riga.*

## Moduli

| Stadio | Libreria | Dove |
|---|---|---|
| Casa (luci, tapparelle, termostato, sensori) | Home Assistant via WebSocket (`websockets`): agente di conversazione integrato per i comandi, stati delle entità esposte per le letture | `calliope/casa/` → `HomeBackend` (`base.py`), `HomeAssistantBackend` (`homeassistant.py`), `Regole` (`regole.py`), `descrivi` (`parole.py`), `diagnose`, `load_casa`; tool in `calliope/tools/casa.py` |
| Errori di HA in italiano normale | i modelli veri delle risposte d'errore di HA (home-assistant-intents) | `calliope/casa/errori.py` → `riformula_errore`, usato da `HomeAssistantBackend._esito` |

## Note dalla sezione «Stato attuale» di CLAUDE.md (fino al 06/10)

  - **Casa via Home Assistant** (01/10, `calliope/casa/`): luci, tapparelle, termostato,
    prese e sensori, solo entità esposte ad Assist; serrature, allarme, cancello e porta del
    garage solo in lettura. Provata con un HA finto: l'HA vero non è ancora collegato. *[Superato il 01/10 sera: prima prova con l'HA vero, vedi sotto «Prima prova con l'HA vero».]*

## Note dalla sezione «Problemi noti» di CLAUDE.md (fino al 06/10)

- **Casa via Home Assistant** (01/10, `calliope/casa/`, `calliope/tools/casa.py`, prove
  `prove/prova_casa_ha.py`, `prove/prova_casa_ha_ollama.py`, sonda manuale
  `prove/sonda_ha.py`). Tutto provato con un HA finto (`prove/ha_finto.py`: server
  WebSocket vero e le frasi italiane vere di HA, con hassil e home-assistant-intents);
  l'HA di casa non è ancora stato contattato. *[Superato: prima prova con l'HA vero il 01/10 sera, qui sotto.]* Scoperte, verificate sul sorgente di HA:
  - **Comandi tramite l'agente integrato**, non con le entità in `enum` come proponeva la
    ricerca del 26/09 (5.1): HA risolve già nomi, alias, stanze e piani («spegni le luci al
    piano di sopra»), applica l'esposizione, e i tool non cambiano quando cambia ciò che è
    esposto (un `enum` di entità cambierebbe il prefisso del prompt). Il prezzo è che il
    modello deve scrivere nella forma di HA: lo aiutano gli esempi nella descrizione, una
    **riscrittura locale** quando HA non capisce («la presa della TV» → «presa TV», «al 30
    per cento» → «imposta la luminosità di … al 30%», refusi nel nome) e, se non basta, i
    nomi più vicini al modello, che riprova una volta; al secondo errore la frase è fissa.
  - L'id dell'agente integrato è `conversation.home_assistant` (la documentazione dice
    ancora `home_assistant`). **Non chiede conferme né PIN**: per una serratura esposta
    «sblocca la porta» chiama `lock.unlock`; le porte del garage sono `cover` ed esposte di
    predefinito. Per questo ogni comando passa prima da `conversation/agent/homeassistant/debug`
    (riconosce senza eseguire: intent e bersagli), poi dalle regole di Calliope, poi da
    `conversation/process`. Le regole: solo bersagli esposti, `lock` e
    `alarm_control_panel` e i `cover` garage/gate in sola lettura, scene/script/automazioni
    solo da `casa_consentiti`, mai frasi o automazioni personalizzate della casa, l'ospite
    niente salvo `casa_ospite_domini`.
  - `homeassistant/expose_entity/list` e la verifica a secco vogliono un token di un
    **amministratore**. Da verificare sull'HA vero: l'elenco contiene solo le entità di cui
    HA ha già deciso l'esposizione (`should_expose` salvato); la sonda dice quante sono.
  - Le letture non passano da HA: gli intent di HA leggono la temperatura di una stanza
    solo dai termostati e non capiscono «cosa c'è acceso?». `casa_stato` legge gli stati
    tenuti aggiornati da `subscribe_entities` (solo entità esposte) e risponde con una frase
    pronta, in ~0 ms.
  - Comandi e letture finiscono con `risposta_finale` (la frase di HA, o quella di
    Calliope): niente seconda passata del modello. Prova su Ollama: 46/46 in 2 giri, prima
    frase mediana 0,34 s (verifica + esecuzione sull'HA finto: 5–15 ms). «Puoi collegarti
    alla domotica?» chiamava `casa_integrazione` 3 volte su 4 finché il prompt non ha
    nominato la domotica. Con i tool della casa registrati `prova_pc_ollama` 31/31,
    `prova_casa` 21/21, `prova_documenti_ollama` 17/17, tempi invariati. Il distrattore
    «alza il volume del computer» resta a `pc_volume`, «blocca il PC» a `pc_blocca`.
  - **Riassunto dello stato della casa nel messaggio prima della domanda: provato e
    scartato.** La prima frase scendeva a 0,12 s, ma con il riassunto il modello smetteva
    di chiamare *tutti* i tool: ora inventata (15:42 e 10:45 invece delle 17:10), conti a
    mente, luce «già accesa» senza comando.
  - Tempo massimo: chi parla non aspetta mai più di `casa_connessione_s` per collegarsi né
    `casa_timeout_s` per una richiesta. Se il tempo scade durante l'esecuzione Calliope
    dice «potrebbe essere partito lo stesso», non «non risponde». Su Windows una porta
    chiusa su 127.0.0.1 non rifiuta subito: ~1–2 s di tentativi. HA giù all'avvio non
    blocca: ci si ricollega in secondo piano e alla prima richiesta. Dal 02/10 una richiesta
    aspetta un tentativo di collegamento **iniziato dopo di lei** (`_iniziati`/`_finiti`):
    prima bastava la fine di uno qualunque, e con HA appena tornato la prima richiesta poteva
    cadere sul tentativo vecchio fallito. Con HA spento la risposta arriva a
    `casa_connessione_s` + 0,5 (1,5 s nella prova, prima ~1 s).
  - **`prova_casa_ha` stabile** (02/10): falliva 1 volta su 3 nel runner. Oltre alla corsa
    qui sopra, quattro attese fisse (0,15–0,5 s: evento di HA, connessione chiusa, rilettura
    dell'esposizione, richiesta lenta finita) e una verifica con 0,3 s di tempo che sotto
    carico scadeva già lei. Ora la prova aspetta la condizione (`aspetta`, fino a 5 s) e la
    verifica lenta ha 1 s. 22 volte di fila e 15 a 5 in parallelo: tutte passate. Dura ~12 s
    invece di ~9.
  - Il token sta in un oggetto che non si stampa (`repr`, `vars`, traceback); un errore di
    PyYAML su `segreti.yaml` dice solo la riga (il messaggio intero conterrebbe il token).
  - Due frasi di HA ritoccate: «Ho aperto tutte le tapparella» (HA ripete la parola
    detta) e «le luci in piano di sopra».
  - **Prima prova con l'HA vero** (01/10, un Raspberry Pi, HA 2026.9): certificato DuckDNS
    verificato con `casa_tls_nome` collegandosi all'IP; molte entità esposte
    **irraggiungibili** (dispositivi vecchi o doppi, con nomi quasi uguali), molte senza stanza,
    quasi tutti i termostati con il nome della stanza. Comandi in 0,08–0,22 s sul Pi («accendi /
    spegni le luci in taverna»). Corretti in `casa/parole.py`: le entità irraggiungibili si
    saltano se ce ne sono di vive (una frase sola se sono tutte morte), niente frasi
    ripetute, un dispositivo con il nome della stanza si dice «il termostato in camera» e
    non vince sulla stanza nominata; `casa_stato` cerca prima con la frase detta se il
    modello ha perso il tipo («quali luci sono accese?» → «cosa c'è acceso»).
  - **Nomi uguali e nome detto tale e quale** (01/10, sera): «accendi l'interruttore
    taverna» non lo capiva HA (non conosce «l'interruttore X») e la riscrittura locale non
    partiva perché c'erano due entità «Taverna», una irraggiungibile. Ora `riscrivi`
    preferisce le entità vive e tratta più entità con lo stesso nome come un nome solo; se
    nella frase c'è un nome identico (normalizzato) a un'entità visibile riprova **una**
    volta con «<verbo> <nome>» (`nome_esatto`). I suggerimenti non ripetono un nome e
    mettono prima quelli delle entità vive. Prova con l'HA finto (due «Taverna», una
    unavailable); `prove/ha_finto.py` ora non accende le entità irraggiungibili.
  - **Pronomi e «l'ultima stanza»** (02/10, `Brain.set_reference`, `REFERENCE_MSG`): dopo
    «chiudi taverna» → «Ho spento Taverna», «Scendila» portava a «a quale dispositivo?» e
    «accendi l'ultima stanza che abbiamo spento» a «dimmi il nome della stanza». Un comando o
    una lettura riuscita (≤ 3 entità) mette nel risultato `riferimento` (nomi, stanza,
    comando); Brain lo toglie e, nei turni dopo, lo mette prima della domanda (dopo i ricordi,
    prima dell'azione in sospeso) finché non ne arriva un altro o passano
    `casa_riferimento_s` (300 s); si azzera quando Calliope dorme. Nel registro
    `riferimento_casa`. Il testo conta: misura con Ollama e l'HA finto, ricordi davanti, 8
    scenari (vedi il commento di `REFERENCE_MSG`): senza 25/35, frase descrittiva 40/80 (e
    «accendila» da 5/5 a 0/10), quella scelta, con l'ordine «chiama subito… senza chiedere
    quale» e la riga sul verbo storpiato, 39/40; 10 giri con il codice finale **78/80**
    (prima frase mediana 0,41 s): «Scendila» 8/10, le 2 volte mancate il modello dice «Ho
    spento Taverna» senza tool e la rete lo ferma. Casi contrari («accendi la luce della
    cucina» dopo Taverna, «che ore sono?») 20/20. In `prova_casa_ha_ollama` 6 casi nuovi
    («Accendila» dopo «chiudi taverna», «l'ultima stanza», «Abbassale»…): 12/12 in 2 giri.
  - «Chiudi»/«apri» una luce o un interruttore (`parole._verbo_per`, solo nella riscrittura
    dopo un «non capito» di HA): diventa «spegni»/«accendi»; HA li accetta solo per
    tapparelle e porte. «chiudi taverna» passato tale e quale dal modello falliva 5 volte su
    10 nella misura.
  - `casa_integrazione` c'è anche senza casa configurata: dice a che punto è e il passo
    successivo (`calliope.casa.diagnose`, funzione pura con `stato`, `codice`, `motivo`,
    `prossimo_passo`, `dettagli`, pronta per un registro delle capacità). Dettagli solo a
    chi amministra; ai familiari «chiedi a chi amministra». Con `per_iscritto` prepara la
    guida in PDF o Word dal testo fisso di `casa/guida.py` (`Documenti.scrivi_fisso`, niente
    LLM). Il token non si detta mai: Calliope dice dove incollarlo.
  - **Frasi d'errore di HA** (01/10, `calliope/casa/errori.py`): «Mi dispiace, nell'area
    Taverna il dominio light non è stato esposto.» diventa «In taverna non posso comandare
    nessuna luce: non è esposta ad Assist in Home Assistant.». I 29 modelli sono la copia
    di quelli italiani veri (home-assistant-intents 2026.9.30, sezione `errors`), confrontati
    con il pacchetto installato in `prova_casa_ha` (un cambio di testo in HA si vede);
    domini e classi detti con il nome e il genere («nessuna tapparella», «nessun
    interruttore»). Prima i modelli con più segnaposto: «il dispositivo X nell'area Y» va
    preso prima di «il dispositivo X», che altrimenti lo mangiava intero. Una frase che non
    corrisponde resta com'è, salvo parole tecniche (dominio, classe, entità): allora una
    frase per codice (`no_valid_targets`, `no_intent_match`, `failed_to_handle`). L'HA finto
    ora risponde con i testi veri (`errore_ha`, `errori_forzati`).
