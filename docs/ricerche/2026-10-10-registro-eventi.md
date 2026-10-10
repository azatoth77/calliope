# La conversazione come registro degli eventi: progetto (10/10/2026)

*Progetto del 10 ottobre 2026, dopo la decisione di Dario sul passo 1-bis della macchina a stati
([`2026-10-10-macchina-stati.md`](2026-10-10-macchina-stati.md) § 10.1 e § 10.2): «una voce sola» si
fa **direttamente nella versione forte**, la conversazione come registro degli eventi, senza la
versione incrementale. Fatto sul codice di `main` a e4b09f2. **Nessuna modifica al codice.** Gli
script di conteggio (frasi pronte e domande nel codice) sono nella cartella temporanea della
sessione, non nel repository. Nomi e dati degli esempi sono di fantasia.*

*Aggiunte di Dario durante il lavoro (10/10): i costi della versione forte gestiti e controllati di
continuo, con guardie misurabili (§ 10); ciò che oggi funziona proprio perché le copie sono
separate, da conservare in modo esplicito (§ 11); **un registro per conversazione**, non uno
globale, con ciò che attraversa le conversazioni progettato a parte (§ 2.5).*

## In breve

**Il problema.** Oggi le parole di Calliope hanno tre copie con vite diverse: la **storia del
modello** (`Conversazione.history`), mantenuta a mano da Brain con una trentina di punti che
aggiungono, tolgono, riscrivono e sigillano messaggi; il **registro dei turni** (`TurnLog`, una riga
JSON per turno, con «risposta» = ciò che è andato alla voce); e **ciò che va al TTS**, che parte da
48 chiamate a `say`/`say_cached` sparse in `ciclo.py` e `main.py` più lo stream del modello. Delle
48, **37 non lasciano niente nella storia** (26 escluse le frasi d'attesa, i saluti e le chiusure
volute) e in **sei meccanismi** la storia dice una cosa diversa da quella sentita (§ 1). Le domande
che il codice fa a voce diventano una proposta solo se il testo **finisce** con «?»: il caso del
10/10 alle 07:17 («Chiudo lo sviluppo…? Se vuoi solo una pausa…») ha fatto rifare la stessa domanda
sei volte, e il modello, a cui la persona lo spiegava, rispondeva che «il sistema richiede una
conferma» senza sapere che cosa avesse chiesto.

**La proposta.** **Un registro per conversazione** (per persona o per corsia, come le
conversazioni di oggi), non un registro globale: «fonte unica» vuol dire che **ciascuna**
conversazione ha una sola fonte invece delle tre copie. Il registro è **in sola aggiunta**: gli
eventi (detto dalla persona, detto da Calliope frase per frase con autore e interruzione,
chiamate ed esiti dei tool, proposte aperte e chiuse, compressioni, chiusure). Tutto il resto è
una **proiezione**, cioè una funzione pura degli eventi: il contesto del modello, lo stato della
macchina a stati, il registro dei turni, l'archivio delle conversazioni, la scheda «Conversazione»,
la risposta scritta sugli schermi. Un'**uscita unica verso la voce** scrive l'evento e manda la
frase al TTS nello stesso gesto. Le domande sono **oggetti** (proposte della macchina), non punti
interrogativi nel testo. La garanzia, per costruzione: **l'ultimo messaggio dell'assistente nel
contesto è ciò che la persona ha sentito**, con un'eccezione chiusa e dichiarata (le frasi d'attesa).

**Costo e piano.** Sei passi, ognuno con le sue prove, le sue guardie e un interruttore di ritorno
(`eventi: spento | ombra | attivo`); il primo scrive gli eventi **accanto** alla storia di oggi e
confronta le due proiezioni turno per turno. Stima: **4–5 giorni** di lavoro d'agente (più dei 2–3
del § 10.2: i punti da migrare sono 48 voci e ~30 modifiche della storia, non una manciata).
Latenza: nessuna scrittura su disco nel percorso della prima frase; la ricostruzione del contesto
costa qualche millisecondo e tiene la cache del prefisso **meglio di oggi** (§ 5).

## 1. Inventario: chi parla e chi tocca la storia oggi

Legenda della colonna «nella storia»: **testuale** = la storia ha esattamente ciò che si è sentito;
**diverso** = la storia ha altro (di più, di meno, o testo mai detto); **niente** = si sente ma la
storia non lo sa. «Voluto» segna i casi in cui oggi il «niente» è una scelta (fuori da una
conversazione o segnali).

### 1.1 Le parole di Calliope verso la voce (48 chiamate più lo stream del modello)

| # | Dove (file:funzione) | Che cosa si sente | Nella storia |
|---|---|---|---|
| 1 | `ciclo.py:_rispondi` → `_frase_da_dire` → `_di_frase` (2781) | la risposta del modello, frase per frase | **diverso** se `_frase_da_dire` cambia la frase: `strip_tool_mentions`, `speak_tool_names`, frase taciuta (`annuncio_tool_taciuto`), `clean_for_speech` (asterischi, simboli), `strip_false_citation` («secondo Wikipedia» tolto). La storia tiene il testo **del modello**, non quello detto |
| 1a | dentro `Brain._reply`: testo del modello | — | testuale (salvo il punto 1) |
| 1b | `Brain._reply`: frasi pronte dei tool (`finals`, `risposta_finale`) | la frase del tool, senza seconda passata | testuale (messaggio dell'assistente con la frase) |
| 1c | `Brain._reply`: «Non ci sono riuscita: puoi ripetere la richiesta?» (5 punti) | frase fissa | testuale; **è una domanda e non è una proposta** |
| 1d | `Brain._reply`: `conferma_al_posto_del_vuoto` | la conferma del tool | testuale |
| 1e | `Brain._reply`: dichiarazione già detta e poi vera (`claim_at`) | «Ho acceso la luce» detta prima del tool | **diverso**: `del self.history[claim_at]` toglie una frase **sentita** |
| 1f | `Brain._sviluppo_coda` → `_aggiungi_detto` | «Intanto restiamo sullo sviluppo di…», promemoria del giorno | testuale (attaccata alla risposta) |
| 1g | `Brain._sfida_reply` | `SFIDA_*`, frase finale del tool dopo la sfida | testuale |
| 1h | `Brain.stream_continuation` (ricerca promessa, `ciclo.py:3148`) | la continuazione | testuale, ma come **secondo** messaggio dell'assistente di fila |
| 2 | `ciclo.py:_prepara_risposta.announce` (2466), `_ricerca_promessa` (3134), `_rispondi` coda (2580), `main.py` ripiego dello STT (371), `FRASE_DURA` | frasi d'attesa (`ToolSpec.announce` di 10 tool, `FRASI_CORREZIONE`, `FRASE_CODA`, «Controllo nella biblioteca.», `stt.ATTESA`) | niente (voluto: `say_cached` non entra in `played`) |
| 3 | `ciclo.py:_chiusure` (2320) | cortesia («Prego!») | testuale (`record_courtesy`) |
| 4 | `ciclo.py:_secondo_cancello` (647) | `guardia.PROTEZIONE` | testuale (`record_courtesy`) |
| 5 | `ciclo.py:richieste_al_tutore` (766) | «Intanto: … Va bene?» | testuale (`record_announcement`) e proposta |
| 6 | `ciclo.py:_annuncia_documenti` (1014), `_annuncia_installazioni` (1032), `_annuncia_lavori` (1065), `_annuncia_estensioni` (1092) | annunci (dopo `riferire.controlla_testo` per agente ed estensioni) | testuale (`record_announcement`, con `_fonte` per i non fidati); la proposta solo se finisce con «?» |
| 7 | `ciclo.py:_cassetto_dopo` (1299) | revisione del cassetto, con la domanda «Vuoi che li tenga…?» | testuale, **domanda senza proposta** |
| 8 | `ciclo.py:_modulo_dallo_schermo` (1319) | frase dopo un modulo | testuale, più un messaggio della persona sintetico «(Ho scritto sullo schermo i dati…)» (`schermi/moduli.py:completa_modulo`) |
| 9 | `ciclo.py:3148` | continuazione della ricerca promessa | testuale (vedi 1h) |
| 10 | `ciclo.py:_annuncia_agenda` (1000) | timer e promemoria scaduti | **niente**: a «spostalo di cinque minuti» il modello non sa quale |
| 11 | `ciclo.py:avvisi_ai_tutori` (706) | avvisi ai tutori | **niente** |
| 12 | `ciclo.py:errore_nel_giro` (799), `_rispondi` eccezione (2624) | «Scusa, ho avuto un problema…» | **niente** (e la storia può avere la risposta a metà) |
| 13 | `ciclo.py:_inizio_giro` (933), `_esito_registrazione` (1968–1997, 7), `_arruolamento` (1919, 1939), `_dopo_la_risposta` (3099), `_inizia_primo_utente` (2154) | registrazione della voce | **niente**; «Vuoi dirmi il tuo nome?» è una **domanda senza proposta** (`pending_real_name`) |
| 14 | `ciclo.py:_nome_reale` (2027, 2033, 2043) | «Dimmi pure il tuo nome.», «Ok, ti chiamerò…» | **niente** |
| 15 | `ciclo.py:_solo_il_nome` (2178, 2180) | «Ciao Ginevra.», «Sì?» | **niente**; «Sì?» è una domanda |
| 16 | `ciclo.py:_chiedi_chi_parla` (1878) | `CHI_PARLA` | **niente**, domanda senza proposta |
| 17 | `ciclo.py:_senza_domanda` (1164) | «Ho la foto. Cosa vuoi sapere?», file in attesa | **niente**, domanda |
| 18 | `ciclo.py:_fuori_orario` (2347, 2349), `_protezione_dopo` (2529) | protezione, fuori orario, protezione ripetuta | **niente** |
| 19 | `ciclo.py:_annuncia_giochi` (1111) | frasi dei giochi | niente (voluto: non sono risposte) |
| 20 | `ciclo.py:_addormentati` (2241), `_uscite` (2268, 2284), `_esci_dalla_registrazione` (1952, 1958) | «A presto!», «Mi spengo», «Va bene, ricominciamo da capo.» | niente: la conversazione si chiude **prima** o subito dopo; la chiusura non arriva neanche all'archivio |
| 21 | `main.py:_saluto_ed_eco` (844), `satellite.saluto` (`sintetizza`, 359 e 906) | il saluto | niente (voluto: fuori conversazione) |
| 22 | `ciclo.py:_dopo_interruzione` | **niente** (lo stop non si dice) | **diverso**: `record_stop` scrive «Va bene, mi fermo. (argomento chiuso)», mai detto |
| 23 | risposta interrotta (`Brain.record_interruption`) | le frasi intere fino al nome, più l'inizio di quella interrotta | **diverso**: solo le frasi intere (`played`) più « … (interrotta)»; la frase a metà sparisce |
| 24 | voce muta per un turno scritto (`Speaker.muto`, `rispondi.py`) | niente a voce, la risposta **scritta** sullo schermo | testuale rispetto allo scritto (`" ".join(t.said)`), ma la storia non sa che il canale era lo scritto |

**In numeri.** Chiamate dirette alla voce fuori da `tts.py`: **48** (46 in `ciclo.py`, 2 in
`main.py`), più 8 segnali (`chime`, `suono`) e lo stream di Brain (27 `yield`). Delle 48: **11**
testuali (una, la risposta del modello, solo finché i filtri non cambiano la frase), **37** senza
niente nella storia: 4 frasi d'attesa, 2 voluti (saluto, giochi), 5 chiusure, **26 parole sentite
in una conversazione viva che il modello non vede**. Meccanismi in cui la storia è **diversa** da
ciò che si è sentito: **6** (filtri della frase, `claim_at`, `record_stop`, frase interrotta persa,
`_applica_capito` sul lato della persona, canale scritto non segnato). La verifica su un caso vero
la fa il ramo `sviluppo-chiusura`; i contatori del § 6 la rendono continua.

### 1.2 Domande fatte dal codice

Testi del codice che finiscono con una domanda (scansione AST, esclusi SQL, espressioni regolari e
docstring): **~170** fuori dagli esercizi (gli esercizi ne hanno ~70, che sono domande per natura),
in 35 moduli. I più: `tools/sviluppo.py` 28, `ufficio/servizio.py` 17, `politica.py` + `valore.py`
21, `agenti/servizio.py` 12, `estensioni/servizio.py` 9, `tools/agenti.py` 9, `tools/builtin.py` 8.

Diventano una proposta solo così: il tool restituisce `in_sospeso` **e** la risposta detta finisce
con «?» (`stream_reply`, `said.endswith("?")`), oppure `record_announcement(…, pending)` con lo
stesso controllo. Restano fuori, per costruzione:

| Domanda | Dove | Perché non è una proposta |
|---|---|---|
| «Chiudo lo sviluppo di …? Se vuoi solo una pausa…» | `tools/sviluppo.py:432` | testo dopo la domanda (caso delle 07:17) |
| «Vuoi che fermi anche il lavoro dell'agente?» e le domande dello sviluppo dette dal modello | `tools/sviluppo.py`, `SVILUPPO_MSG` | chieste al modello senza `in_sospeso` |
| «Va tutto bene?» | `cancelli.py` | stato a parte (cancello 1) |
| «Vuoi dirmi il tuo nome?», «Sì?», `CHI_PARLA` | `ciclo.py` | stati della corsia, fuori dalla storia |
| «Cosa vuoi sapere?» (foto o file senza domanda) | `ciclo.py:_senza_domanda` | fuori dalla storia |
| «Vuoi che li tenga…?» | `cassetto.py:632` | `record_announcement` senza proposta |
| «puoi ripetere la richiesta?» | `brain.py` (5 punti) | domanda generica, nessuna azione |
| «Intendevi X?» | `brain.py:4539` | proposta solo se non ce n'è un'altra |
| offerte senza tool («Se vuoi cerco su internet.») | il modello | `chiede_risposta`, solo per la cortesia |

### 1.3 Chi modifica la storia del modello (~30 punti)

| Dove | Cosa fa | Nell'evento |
|---|---|---|
| `Brain._reply` | aggiunge il messaggio della persona con `_prov` | `detto_persona` |
| `Brain._allega_dati` | mette le buste dei dati non fidati **dentro** il messaggio della persona | `dato_in_ingresso` (visibilità propria, § 11) |
| `Brain._accogli_immagini`, `_accogli_allegati`, `descrivi_immagini` (5022) | etichette e descrizioni delle foto nel messaggio della persona; le immagini in memoria | `foto_in_ingresso`, `allegato_in_ingresso`, `descrizione_foto` |
| `Brain._applica_capito` | riscrive la frase della persona con quella «capita» | `trascrizione_capita` (la trascrizione resta) |
| `Brain._reply`, `_turn` | messaggi dell'assistente con `tool_calls`, risultati `tool` | `passata_modello`, `chiamata_tool`, `esito_tool` |
| `Brain._reply` (spinta dell'archivio) | una chiamata sintetica a `conversazione_cerca` | `chiamata_tool(origine="rete")` |
| `Brain._reply` | `history.pop()` della risposta vuota, `del history[claim_at]` | niente da togliere: la passata è un evento, il detto è un altro |
| `Brain._trim_history`, `_trim_tokens` | taglio in testa a blocchi | proiezione (finestra) |
| `_compatta_storia` | ora «di allora», risultati lunghi ridotti, **a ogni turno** | forma definitiva del turno, una volta sola (§ 5) |
| `Brain._togli_non_fidati` | contenuto web → `WEB_TOLTO` a fine risposta | visibilità «turno» dell'esito |
| `Brain._seal_private` | riservati e personali → traccia o conferma | visibilità dell'esito |
| `Brain._togli_proposta_rispondi` | via la chiamata e l'esito | tipo escluso dalla proiezione |
| `Brain._aggiungi_detto`, `record_announcement`, `record_courtesy`, `record_stop`, `record_interruption` | aggiungono o riscrivono messaggi dell'assistente | `detto_calliope`, `voce_fine`, `interruzione` |
| `Brain.dimentica_ultimo_turno` | via il turno non rivolto a Calliope | `turno_escluso(non_rivolta)` |
| `Brain._sfida_reply` | turno della sfida | `detto_persona(sfida)`, `chiamata_tool(origine="sfida")` |
| `guardiano.correggi_storia` (da `ciclo._registra_controlli`) | sostituisce la risposta con ciò che è stato detto | sparisce: si scrive già ciò che si dice |
| `schermi/moduli.completa_modulo` | messaggio sintetico della persona, `brain.pending = None` | `modulo_compilato` (solo i nomi dei campi), `proposta_chiusa` |
| `ciclo._archivia_turno` | `_turno` (luogo, canale, sfida) nel messaggio della persona | campi di `detto_persona` |
| `Brain.end_conversation`, `_coda_della_chiusa`, `_inizio_conversazione` | conversazione nuova, coda, ripresa | `conversazione_chiusa`, `conversazione_aperta(ripresa, coda)` |
| `compressione._applica_risultato` | taglio in testa e riassunto | `compressione` |
| `Conversazione.importa` (riavvio) | storia da `correnti` | rigioco degli eventi |
| `corsie.Corsia.turno`, `annuncio_per` | cambiano `brain.conv` | la conversazione è il flusso; la corsia sceglie quale |

## 2. Il modello degli eventi

### 2.1 L'evento

```python
@dataclass(frozen=True)
class Evento:
    conv: str            # id della conversazione (uuid breve, nuovo a ogni apertura)
    seq: int             # 1, 2, 3… dentro la conversazione, senza buchi
    t: float             # time.time() (per il disco) — il monotonic resta in memoria
    tipo: str            # dall'elenco chiuso TIPI (§ 2.2)
    turno: int           # numero della risposta (Conversazione.turn_number)
    vis: str             # visibilità decisa alla scrittura (§ 11.1): modello | turno | schermo | registro | mai
    dati: dict           # i campi del tipo; solo JSON
    v: int = 1           # versione del tipo (rigioco dei registri vecchi)
```

**Un registro per conversazione.** L'oggetto è `RegistroConversazione` (uno per `Conversazione`,
`persona:<id>` o `ospite:<corsia>` come oggi, con un `conv` nuovo a ogni apertura); **non esiste**
un registro globale né un'API che legga gli eventi di più conversazioni insieme. **Identità**:
`(conv, seq)`; l'ordine dentro una conversazione è quello di `seq`, e fra conversazioni non serve
un ordine totale. L'isolamento fra persone è il **comportamento predefinito**: la proiezione riceve
il registro di una conversazione e basta. Ciò che deve attraversare le conversazioni passa da porte
esplicite (§ 2.5).

### 2.2 I tipi

| Tipo | Campi principali | Note |
|---|---|---|
| `conversazione_aperta` | chiave, owner, come (`persona`, `ripresa`, `continua`, `anonima`…), luogo, riassunto di ripresa o coda | ripresa e coda sono il loro testo, non un riferimento |
| `conversazione_chiusa` | motivo (`scaduta`, `nuova`, `esci`, `altra_persona`…) | dopo, nessun evento con lo stesso `conv` |
| `detto_persona` | testo (trascrizione), canale (`voce`, `scritto`, `modulo`), come (`identified_by`), sicurezza della voce, satellite o schermo, sfida (bool), parole incerte | il testo della sfida non si scrive (vis `mai` per le parole) |
| `trascrizione_capita` | prima, dopo, accettata | la proiezione usa «dopo» solo se accettata |
| `dato_in_ingresso`, `foto_in_ingresso`, `allegato_in_ingresso` | fonte, busta (o riferimento in memoria), nome | foto e allegati: solo riferimento, mai su disco (come oggi) |
| `dati_del_turno` | blocchi `[{nome, testo, caratteri}]` | vis `turno`: entrano solo nel prompt del turno; su disco i nomi e le lunghezze |
| `passata_modello` | n, spinta (nome), testo generato, trattenuto (tipo), chiamate | vis `registro`: per il rigioco e la diagnosi |
| `chiamata_tool` | id, nome, argomenti, passata, origine (`modello`, `sfida`, `traduzione`, `rete`) | |
| `esito_tool` | id, ok, contenuto, riservato, personale, non_fidato, correggibile, frase pronta, `in_sospeso` | vis per tipo di tool (§ 11.1) |
| `detto_calliope` | testo detto (dopo `_frase_da_dire`, prima della pronuncia), autore (`contenuto`, `atto`, `esito`), atto (nome, se è un atto), frase (indice nel turno), canale (`voce`, `scritto`, `muta`), satellite, fonte (per gli annunci non fidati) | scritto **all'invio** (§ 3.2) |
| `voce_fine` | turno, sentite (indice dell'ultima frase intera), interrotta, pezzo parziale (testo, se il satellite lo dice) | scritto quando la voce ha finito o è stata interrotta |
| `interruzione` | seme (nome sentito), durante la frase i | |
| `proposta_aperta` | id, tool, argomenti, domanda, cosa, origine, effetto, tipo (`si_no`, `dato`), chi, satellite, scade, turni | scritto **quando la domanda è stata sentita** |
| `proposta_chiusa` | id, come (`si`, `no`, `correzione`, `rinvio`, `scaduta_tempo`, `scaduta_turni`, `sostituita`, `persa_stop`, `persa_uscita`, `persa_cancello`, `persa_riavvio`), eseguita | ogni chiusura ha il suo nome (oggi la scadenza è silenziosa) |
| `sfida_chiesta`, `sfida_esito` | proposta, tentativi, esito | le parole della sfida mai su disco |
| `modulo_compilato` | modulo, campi (nomi, mai i valori) | |
| `turno_escluso` | turno, motivo (`non_rivolta`) | la proiezione salta tutto il turno |
| `compressione` | fino a `seq`, riassunto (testo e dati), usato | |
| `turno_chiuso` | esito, regole, tempi (STT, prima frase, prima voce), contesto (token, `lettura_s`, riletti), controlli | sorgente del registro dei turni |

**Tre categorie del parlato** (`autore` di `detto_calliope`, § 4): `contenuto` (parole del modello),
`atto` (atto di dialogo della macchina o del ciclo, testo fisso con un nome), `esito` (frase pronta
di un tool). Le frasi d'attesa sono `atto` con il nome `attesa_*`.

### 2.3 Persistenza

- **In memoria** ogni `Conversazione` tiene la sua lista di eventi (`eventi: list[Evento]`), la
  fonte per il processo che gira. Aggiungere un evento è un `append` sotto il lock della
  conversazione (§ 11.7): microsecondi.
- **Su disco**: i registri delle conversazioni stanno in una tabella `eventi` di
  `conversazioni.db` (stesso file e stesso thread dell'archivio, WAL, scrittura a lotti a fine frase
  e a fine turno), **partizionata per conversazione**: ogni lettura e ogni cancellazione è per
  `conv` o per `persona`, mai «tutto». Un file per conversazione è stato valutato: isolamento fisico
  più netto, ma migliaia di file, «dimentica» e rotazione da fare sul file system, e nessun
  vantaggio per la voce; la tabella con la chiave di partizione è la scelta. Chiave `(conv, seq)`,
  colonne `t`, `tipo`, `turno`, `persona`, `ospite`, `dati` (JSON già filtrato per il disco,
  § 11.1). **Sola aggiunta** per costruzione dell'API: nessun `UPDATE`; `DELETE` solo da «dimentica»,
  dalla rotazione e dalla chiusura degli ospiti (§ 10).
- **Riavvio**: le conversazioni non chiuse e non scadute si ricostruiscono **rigiocando** i loro
  eventi (sostituisce la tabella `correnti`, che oggi salva la storia intera a ogni turno). Una
  `proposta_aperta` senza chiusura diventa `proposta_chiusa(persa_riavvio)` (decisione di Dario:
  una proposta si perde al riavvio); rifiuti e intenzioni si ricostruiscono dagli eventi, e non si
  perdono più (§ 1.10 punto 11 della macchina a stati).
- **Rotazione**: dopo `eventi_giorni` (proposta: 7) gli eventi di una conversazione chiusa si
  riducono alla forma dell'archivio (`turni`, che c'è già e che la ricerca usa) e si cancellano.
  L'archivio resta la memoria lunga; il registro degli eventi è la memoria **fine** e breve.

### 2.4 Privacy e dati per persona

- **Per persona**: ogni evento ha `persona` (id del profilo) o `ospite`. «Dimentica» (oggi
  `conversazioni.dimentica`, tool `conversazione_dimentica`) cancella **le righe** di tutte le
  conversazioni della persona, con `PRAGMA secure_delete` e un checkpoint del WAL, poi le proiezioni
  che ne derivano (archivio, cronologia delle schede, `correnti` finché esiste); le conversazioni
  in memoria della persona si chiudono e si svuotano (§ 10.1).
- **Ospiti**: come oggi nessun testo nel registro dei turni; gli eventi con testo di una
  conversazione `ospite:` si cancellano alla sua chiusura, tenendo solo ciò che l'archivio tiene
  già oggi.
- **Minori**: stesse regole di una persona, più quelle di oggi: un turno fermato dal guardiano ha
  `detto_persona` con vis `mai` per il testo su disco (oggi `rec["testo"] = None`); i segnali dei
  cancelli restano in `cancelli.json`, non negli eventi.
- **Mai su disco** (come oggi): foto, allegati, testi dei siti, parole della sfida, codici di
  abbinamento (`redact`), risultati dei tool riservati (solo la traccia).

### 2.5 Ciò che attraversa le conversazioni

Con un registro per conversazione, ogni passaggio fra conversazioni è una **porta esplicita**, con
un nome, una prova e una riga nel registro dei turni. Nessuna porta copia eventi da un registro a
un altro: si scrive un evento **nuovo** nel registro di destinazione, con la sua visibilità.

| Cosa attraversa | Oggi | Con un registro per conversazione |
|---|---|---|
| **Annunci e risultati dei lavori dell'agente** consegnati a una persona | la coda degli annunci; `corsia.annuncio_per(brain, item["chi"])` sposta la corsia sulla conversazione della persona e `record_announcement` scrive nella storia | la corsia che lo dice scrive `detto_calliope(autore="esito", atto="annuncio_lavoro", fonte="agente")` nel registro di `item["chi"]` (mai «di chi ha parlato per ultimo», buco 5); senza una conversazione aperta della persona se ne apre una (`conversazione_aperta(come="annuncio")`), come fa oggi `di_persona(crea=True)` |
| **Documenti, installazioni, estensioni, agenda** | come sopra; l'agenda non scrive niente | come sopra, nel registro di chi li ha chiesti (`owner`, `item["chi"]`; per l'agenda l'origine già salvata da `rispondi.segna`) |
| **Eventi della casa** (stato dei dispositivi, meteo) | non sono nella storia: il riferimento all'ultimo dispositivo è della conversazione (`reference`), lo stato si legge col tool | invariato: la casa resta **fuori** dai registri (dati letti dai tool, `esito_tool`); il riferimento diventa un fold degli esiti della conversazione |
| **Compagnia** (più voci allo stesso satellite) | `Compagnia` per corsia; ogni frase va nella conversazione di chi parla, la frase incerta nella `ospite:<corsia>` | invariato: la frase va nel registro della persona riconosciuta, quella incerta nel registro anonimo della corsia; lo stato della compagnia resta della corsia (non è un evento di una persona) e nel `detto_persona` c'è solo `compagnia: true` |
| **Avvisi ai tutori** dal guardiano | `minori.avvisi()` in SQLite, detti dopo la risposta al tutore riconosciuto; niente nella storia | il registro del **minore** ha il suo turno (con le regole di oggi sul testo); l'avviso resta nella tabella degli avvisi (fuori dai registri), e quando lo si dice al tutore diventa `detto_calliope(atto="avviso_tutore")` nel registro **del tutore**, con il testo dell'avviso e mai le frasi del minore |
| **Coda della conversazione** alla stessa persona | `_coda_della_chiusa`: gli ultimi scambi nel riassunto della nuova, solo stessa chiave e mai `ospite:` | proiezione della conversazione chiusa (gli ultimi scambi detti) scritta come `conversazione_aperta(coda=…)` nel registro nuovo **della stessa chiave**; la porta rifiuta una chiave diversa (prova del buco 6) |
| **Ricerca nell'archivio** fra conversazioni (`conversazione_cerca`, ripresa) | l'archivio `turni` con FTS e vettori, filtrato per persona | invariata: l'archivio è un **indice** derivato dai registri a turno finito, con il filtro per persona di oggi; il risultato entra nel registro corrente come `esito_tool` (dati fidati della persona stessa) |
| **Statistiche globali** (`calliope stato --turni`, cruscotto, attrito) | il registro dei turni, un file al giorno | invariate: il registro dei turni resta un **indice globale** costruito dalle proiezioni `turno_chiuso` di tutti i registri, senza testo dove oggi non c'è |
| **Proposta altrui** («c'è una proposta di Ginevra in sospeso») | `proposta_altrui` legge la `pending` della conversazione di prima della corsia | la porta legge dal fold di quel registro solo `{chi_nome, domanda, cosa}` (mai altri eventi), solo per lo stesso satellite e solo entro i tempi della proposta |
| **Profili, ricordi, rifiuti di sicurezza** | memoria (`memory.py`), profili, `Instradamento._persone` | fuori dai registri (non sono conversazione); i ricordi entrano nel turno come `dati_del_turno` |

Prova `prova_eventi_porte`: ogni scrittura in un registro da un'altra conversazione passa da una
delle porte dell'elenco (AST: nessuna chiamata a `RegistroConversazione.aggiungi` con un registro
che non sia quello della corsia o quello restituito da una porta).

## 3. Le proiezioni

Ogni proiezione è una **funzione pura** `(eventi, configurazione) → vista`, senza stato nascosto:
le eccezioni stanno negli eventi (un turno escluso, un esito riservato), non nella proiezione.
Il modulo: `calliope/eventi/` con `tipi.py`, `registro.py` (scrittura, lock, disco), `proiezioni.py`.

### 3.1 Il contesto del modello

```
sistema · riassunto (dall'ultima `compressione`) · turni chiusi (forma definitiva) · turno n-1
(forma viva) · blocco dello stato e dati del turno (vis turno) · frase della persona · spinte
```

Regole, una per tipo (tabella `PROIEZIONE_CONTESTO`, ogni tipo una riga o `ESCLUSO` con il motivo):

- **Persona**: `detto_persona` (con `trascrizione_capita` accettata), le buste dei dati in
  ingresso nel turno in cui sono arrivate, le etichette delle foto, `modulo_compilato` come oggi
  «(Ho scritto sullo schermo i dati per …: …)».
- **Calliope**: per ogni turno **un** messaggio dell'assistente con il testo di tutti i
  `detto_calliope` sentiti (fino a `voce_fine.sentite`), nell'ordine, chiamate dei tool comprese
  nella posizione in cui sono avvenute. Esclusi solo gli atti `attesa_*` e i segnali (elenco
  chiuso). Una risposta interrotta finisce con il segno « … [interrotta]» (l'unica annotazione non
  detta, anch'essa chiusa: § 11.4).
- **Annunci fra un turno e l'altro** (lavori, documenti, agenda, cassetto): `detto_calliope` di
  autore `atto` o `esito`, attaccati all'ultimo messaggio dell'assistente come fa oggi
  `record_announcement`; con `fonte` non fidata la traccia di provenienza (`_fonte`).
- **Tool**: nel turno in corso tutto (chiamate ed esiti per intero: servono alla passata dopo);
  nel turno n-1 le chiamate **riuscite** con l'esito intero se breve (≤ 400 caratteri: «e dove è
  nato?»); nei turni prima la **forma definitiva**: esito compatto (conferma detta o traccia), ora
  «di allora». Sempre esclusi: `proposta_rispondi` (§ 3.8 della macchina a stati), chiamate
  scartate e ripetute, giri di correzione riusciti (resta la chiamata buona), domande e rifiuti
  della politica (la domanda è già nel detto, lo stato è nella macchina). Esiti `non_fidato`:
  interi solo nel turno, poi `WEB_TOLTO`; riservati e personali: traccia o conferma dal turno dopo
  (oggi `_seal_private` a fine risposta: uguale).
- **Promemoria non parlati** (§ 4.3): nel blocco dello stato del turno, mai nella storia.
- **Riassunto**: il testo dell'ultima `compressione` subito dopo il sistema; i turni prima di
  `fino_a` non si proiettano.
- **Finestra**: il taglio in testa a blocchi (`_trim_history`, `_trim_tokens`) diventa un indice
  di partenza della proiezione, sempre su un turno, deciso dal conto dei token come oggi.

**Garanzia** (prova del § 6): per ogni turno chiuso, il testo dell'assistente proiettato, tolto il
segno d'interruzione, è uguale alla concatenazione delle frasi sentite registrate nel turno, attese
escluse. Non è una regola che si rispetta: è come la proiezione è scritta.

Il blocco dello stato, i dati del turno e le spinte restano **dove sono oggi** (dopo la storia,
prima della frase): effimeri, nel registro come `dati_del_turno` per il rigioco.

### 3.2 La voce: un'uscita sola

```python
class Uscita:                         # una per corsia, intorno allo Speaker di oggi
    def di(self, testo: str, autore: str, atto: str | None = None, *, fonte=None) -> None:
        ev = self.registro.aggiungi("detto_calliope", testo=testo, autore=autore, atto=atto,
                                    frase=self._i, canale=self._canale(), fonte=fonte)
        self._i += 1
        self.speaker.say(testo)       # o say_cached per gli atti attesa_*
    def fine(self) -> None:           # dopo speaker.wait(): `played` e l'interruzione
        self.registro.aggiungi("voce_fine", sentite=…, interrotta=…, parziale=…)
```

- **Streaming frase per frase preservato**: l'evento si scrive **all'invio** della frase (in
  memoria, prima di `say`), non dopo la sintesi; la voce non aspetta niente. Quanto si è sentito
  si sa solo a fine turno (`played`, o `fine_turno` del satellite), e lo dice `voce_fine`. Scrivere
  a fine frase vorrebbe dire aspettare la riproduzione dentro il ciclo delle frasi, e costerebbe
  la sovrapposizione sintesi/riproduzione (principio 6): scartato.
- **Il testo dell'evento** è quello mandato a Piper **prima** della pronuncia (`pronuncia.py`
  cambia solo il testo dato a Piper, dentro `_pcm`): «file», non «fàil» (§ 11.3).
- **Interruzione**: `voce_fine.interrotta` e `sentite`; il pezzo della frase interrotta, se il
  satellite dice fin dove è arrivato, in `parziale` (oggi si perde).
- **Prova statica**: fuori da `calliope/eventi/uscita.py` e `tts.py` nessuna chiamata a `say`,
  `say_cached`, `chime`, `suono`, `sintetizza` (il saluto passa da `Uscita.saluto`, fuori
  conversazione, dichiarato).

### 3.3 La macchina a stati

`StatoPersona` di `stato_dialogo.py` diventa un **fold** degli eventi della conversazione: la
proposta aperta è l'ultimo `proposta_aperta` senza `proposta_chiusa`; la sfida, le intenzioni, i
rifiuti, l'attività (sviluppo, esercizi) allo stesso modo. Le transizioni sono eventi: il campo
`dialogo_ombra` del registro dei turni si ricava, non si calcola a parte. Il fold è incrementale
(si aggiorna a ogni evento) e verificato a ogni riavvio rigiocando da capo.

### 3.4 Il registro dei turni

`TurnLog.write` riceve la riga costruita da `turno_chiuso` più gli eventi del turno: stesso formato
JSONL di oggi (così `calliope stato --turni`, `revisione.py`, il cruscotto e gli script di misura non
cambiano), stessa privacy (ospiti senza testo, minori fermati, sfida, segreti). `risposta` = frasi
sentite; `risposta_inviata` = frasi inviate quando sono diverse. Gli annunci, le installazioni e i
giochi che oggi scrivono righe proprie diventano turni senza `detto_persona`.

### 3.5 Archivio, scheda «Conversazione», cronologia, risposta scritta

- **Archivio** (`conversazioni.db`, tabelle `turni` e FTS): la funzione `conversazione.turni(...)`
  di oggi riceve i turni ricavati dagli eventi a turno finito (oggi li ricava dalla storia): stesse
  regole (riservati, oscuramento, sfida, `tipo`). La scheda «Conversazione» e la cronologia
  continuano a leggere l'archivio: non cambiano.
- **Chiusure** («A presto!», «ricominciamo») entrano nell'archivio come ultimo turno della
  conversazione chiusa: oggi si perdono.
- **Risposta scritta** sugli schermi (`rispondi.risposta_scritta`): i `detto_calliope` del turno con
  canale `scritto` o `muta`, non più `" ".join(t.said)` del ciclo.

## 4. Le tre categorie del parlato

**Regola**: ciò che serve al modello non si dice a voce; ciò che si dice a voce il modello lo vede.
Un'indicazione per il modello («se chiede di aprirlo chiama pc_apri_file», «di' che…») sta nel
risultato del tool o nel blocco dello stato, mai in una frase detta; una frase detta non porta
istruzioni.

### 4.1 Contenuto del modello

La risposta del modello (§ 1.1 punti 1, 1a, 1h). Una domanda nel contenuto («Vuoi che cerchi su
internet?») resta del modello: diventa una proposta solo se c'è un tool con `in_sospeso`; altrimenti
è un'offerta senza azione (`chiede_risposta`), che vale per la cortesia come oggi.

### 4.2 Atti di dialogo (testi fissi della macchina o del ciclo)

| Atto | Testi di oggi | Domanda? | Diventa |
|---|---|---|---|
| `attesa_tool`, `attesa_correzione`, `attesa_coda`, `attesa_contesto`, `attesa_biblioteca`, `attesa_stt` | `announce`, `FRASI_CORREZIONE`, `FRASE_CODA`, `FRASE_DURA`, `stt.ATTESA` | no | evento, **esclusi** dal contesto (elenco chiuso) |
| `cortesia` | `cortesia.py` | no | evento (oggi `record_courtesy`) |
| `stop` | niente detto | no | evento `proposta_chiusa(persa_stop)` se serve, **nessun** `detto_calliope` finto |
| `uscita`, `nuova` | «A presto!», «Mi spengo…», «Va bene, ricominciamo da capo.» | no | evento nella conversazione che si chiude |
| `saluto` | «Ciao Ginevra.», «Sì?» | «Sì?» sì | «Sì?» → «Dimmi.»: non è una proposta, non deve essere una domanda |
| `protezione`, `fuori_orario`, `protezione_ripetuta` | `guardia.PROTEZIONE`, `frase_fuori_orario` | no | evento (oggi niente o `record_courtesy`) |
| `cancello_1` | «… Va tutto bene?» | sì | **proposta** della macchina (origine `cancello`, tipo `si_no`), chiude quella di prima (`persa_cancello`) |
| `chi_parla` | `CHI_PARLA`, `SFIDA_CHI_PARLA` | sì | proposta di tipo `dato` |
| `sfida` | «Per conferma ripeti: …» | richiesta | evento `sfida_chiesta`; parole mai su disco |
| `registrazione` | 10 frasi di `_esito_registrazione`, `_arruolamento`, `_nome_reale` | «Vuoi dirmi il tuo nome?» | attività `arruolamento`; il nome è una proposta di tipo `dato` con scadenza |
| `errore` | «Scusa, ho avuto un problema…» | no | evento |
| `ripeti` | «Non ci sono riuscita: puoi ripetere la richiesta?» | sì, senza azione | «Non ci sono riuscita: ripeti la richiesta, per favore.» (non una domanda) |
| `annuncio_*` | agenda, documenti, installazioni, lavori, estensioni, cassetto, avvisi ai tutori, giochi | a volte | evento; con la domanda **solo** come proposta (`Attesa` della macchina) |
| `senza_domanda` | «Ho la foto. Cosa vuoi sapere?» | sì, senza azione | «Ho la foto: dimmi cosa vuoi sapere.» |
| `riga_sviluppo` | «Intanto restiamo sullo sviluppo di…» | no | evento (oggi `_aggiungi_detto`) |

### 4.3 Esiti dei tool (frasi pronte) e promemoria

- Le frasi pronte (`risposta_finale`, `conferma`, `da_dire`: ~175 punti nei tool) restano: si dicono
  senza la seconda passata (27/09, latenza) e diventano `detto_calliope(autore="esito")`.
- **Una frase pronta che chiede** («Lo apro?», «Procedo?», «Chiudo lo sviluppo …?») si spezza in due:
  il tool restituisce la frase **senza** la domanda e un `in_sospeso`; la macchina rende la domanda
  **in fondo** («Lo apro?»), registra `proposta_aperta` quando è stata sentita. Così il caso delle
  07:17 non si può scrivere: il «Se vuoi solo una pausa, dimmi "sospendi"» diventa parte della frase
  prima della domanda, o un promemoria per il modello.
- **Promemoria non parlati** (nel blocco dello stato, mai detti): i `cosa_fare` dei risultati (110
  punti), il `messaggio` proprio delle proposte (`PENDING_MSG`, la domanda dell'agente), la riga
  della fase dello sviluppo (`SVILUPPO_MSG`), «se chiede di aprirlo chiama pc_apri_file». Con
  l'interprete acceso (passo 2 della macchina) si riducono a «se conferma, rispondi alla proposta».

**Prova statica** (§ 6): nessun testo pronto di un tool o del ciclo con «?» se non è la domanda di una
proposta (resa dalla macchina) o di un atto dichiarato; il contatore «domande non registrate» a zero.

## 5. Cache del prefisso e latenza

**Come si legge la cache oggi.** Ollama rilegge il prompt dal primo messaggio diverso dalla volta
prima. I dati del turno stanno prima della frase e cambiano posto a ogni turno: il prompt nuovo
diverge dal vecchio **all'inizio del turno n-1**, e Ollama rilegge da lì (mediana `lettura_s`
0,37 s, § 2.5 della macchina a stati). In più `_compatta_storia` riscrive a ogni turno messaggi più
vecchi (risultati oltre 400 caratteri del turno n-2, l'ora): quando succede la rilettura parte da lì.

**Con gli eventi**:

1. La proiezione è **deterministica** (stessi eventi → stessi byte: chiavi JSON ordinate, nessun
   orario calcolato al momento, la frase d'attesa scelta a caso registrata nell'evento).
2. Ogni turno ha **due forme**: viva (turno n-1) e definitiva (n-2 e prima). Il passaggio avviene una
   volta sola, nel turno in cui il turno esce dalla zona già riletta; le forme definitive sono
   **memorizzate** per `(conv, turno)` e non cambiano più. È la stessa rilettura di oggi nel caso
   peggiore, e meno spesso (oggi la compattazione dell'ora tocca anche turni già definitivi).
3. Gli eventi si **aggiungono in coda**: un annuncio, un'interruzione, una chiusura di proposta
   cambiano solo l'ultimo turno.
4. **Compressione**: l'evento `compressione` cambia tutto dopo il sistema, come oggi: una rilettura
   intera, scaldata in secondo piano (`scalda_conversazione`, che proietterà dagli eventi con lo
   stesso codice). Gli eventi non si cancellano: la proiezione parte da `fino_a`.
5. **Profilo dei tool e cambio di modalità**: invariati (cambiano il prefisso, si scaldano).

**CPU per turno**: il fold e la proiezione di una conversazione (al più qualche centinaio di eventi,
turni definitivi già pronti) costano meno di un millisecondo in Python; la serializzazione per il
disco gira nel thread dell'archivio. Si misura (`contesto_ms`, § 10.2).

**Prima frase (principio 6)**: nessuna scrittura su disco nel percorso; l'`append` in memoria prima di
`say` costa microsecondi; la proiezione si costruisce dove oggi si costruisce `with_memory`. Effetto
atteso nullo, verificato con l'avviso di `calliope stato --turni` (1,2 s) e con `riletti` (§ 10.5).

## 6. Invarianti e prove

| Invariante | Prova a secco (hook) | Contatore (`calliope stato --turni`) |
|---|---|---|
| **Uscita unica** verso la voce | `prova_uscita_unica`: AST, nessuna chiamata a `say`/`say_cached`/`chime`/`suono`/`sintetizza` fuori da `eventi/uscita.py` e `tts.py` | — |
| **Detto = storia** | `prova_eventi_proiezione`: per ogni turno di un giro sintetico (interruzione, annuncio, cortesia, stop, frase filtrata) il testo proiettato = frasi sentite | `parlato_diverso` (deve restare 0); nel passo 1 lo calcola l'ombra contro la storia di oggi |
| **Nessuna domanda fuori da una proposta** | `prova_domande_proposte`: AST sui testi pronti di tool e ciclo, «?» solo negli atti dichiarati e nelle domande rese dalla macchina | `domande_non_registrate`: frasi sentite che finiscono con «?» senza `proposta_aperta` né atto dichiarato (il contenuto del modello conta a parte, come offerta) |
| **Visibilità** (§ 11.1) | `prova_eventi_visibilita`: banco d'attacco di `prova_politica` e di `prova_valore` rigiocato sul registro; la proiezione del modello non contiene mai eventi `mai`, né `turno` fuori dal loro turno, né le parole della sfida, i codici, le buste di turni passati | `fughe_proiezione` (0) |
| **Partizione** (§ 11.2) | `prova_eventi_partizione`: due persone (un adulto e un minore di fantasia) e un ospite su due satelliti insieme; nessun evento di una conversazione nella proiezione di un'altra | — |
| **Porte fra conversazioni** (§ 2.5) | `prova_eventi_porte`: ogni scrittura in un registro di un'altra conversazione passa da una porta dichiarata; annuncio del lavoro nel registro di `chi`, coda solo alla stessa chiave, avviso al tutore senza le frasi del minore | `porte` per nome nel registro dei turni |
| **Proiezioni pure** (§ 10.2) | `prova_proiezioni_pure`: AST, `proiezioni.py` importa solo `eventi.tipi`, `config` e la libreria standard; niente `time`, `random`, attributi di Brain o del ciclo; stessa proiezione due volte e dopo il rigioco dal disco | `contesto_ms` con avviso |
| **Ogni tipo proiettato o escluso** (§ 10.4) | `prova_eventi_tipi`: ogni tipo in `TIPI` ha una riga in `PROIEZIONE_CONTESTO` (resa o `ESCLUSO` con il motivo) e nel registro dei turni | — |
| **Dimentica vera** (§ 10.1) | `prova_eventi_dimentica`: dopo «dimentica» la frase di prova («zafferano viola 42») non c'è nel registro, nelle proiezioni, nei file (`conversazioni.db`, WAL, turni, cronologia: ricerca nei byte) | `dimentica_residui` (0) |
| **Crescita** (§ 10.3) | `prova_eventi_rotazione` | `eventi_mb_giorno` con avviso |
| **Cache** (§ 10.5) | `prova_eventi_prefisso`: due turni di fila, i messaggi fino al turno n-2 identici byte per byte | `riletti` e `cache_rotta` |
| **Rigioco di un giro vero** | `prova_eventi_rigioco` (livello 3, con Ollama): un giro scritto in eventi (nomi di fantasia) rigiocato col modello locale; il contesto ricostruito uguale a quello registrato | — |
| **Riavvio** | `prova_eventi_riavvio`: conversazione aperta, proposta aperta, file troncato a metà riga → stessa proiezione, proposta `persa_riavvio`, nessun arresto | — |

Il rigioco è anche lo strumento di misura: un giro vero della DGX, scritto in eventi, si ricostruisce
sul portatile con il prompt esatto (oggi il § 9 della macchina a stati lo ha dovuto ricostruire a
mano dal codice).

## 7. Rapporto con la macchina a stati

| Passo del § 6 della macchina | Cosa cambia |
|---|---|
| 1 Interprete in ombra (fatto) | `dialogo_ombra` si ricava dagli eventi; il blocco dello stato legge il fold |
| 1-bis «una voce sola» | **è questo progetto** |
| 2 Consenso unico | invariato nella sostanza; `consenso.basta` riceve lo stato dal fold; le tre correzioni del § 10 (il «no» all'analisi, «sospendi» a E1, la proposta sostituita) diventano eventi con il loro nome |
| 3 Priorità della frase | **si semplifica**: la proposta nasce quando la domanda è stata **sentita** (`voce_fine`), quindi una risposta interrotta prima della domanda non apre niente e una interrotta dopo sì (buco 1 del passo 0, per costruzione); lo stop chiude la proposta con un evento |
| 4 Profilo dei tool | invariato |
| 5 Altra persona e tempi | **si semplifica**: una conversazione è un flusso di eventi della persona; «altra persona» non chiude il flusso di prima; la coda della conversazione è una proiezione della conversazione chiusa della **stessa** chiave (buco 6 per costruzione); gli annunci si scrivono nel flusso di `item["chi"]` (buco 5) |
| 6 Dati del turno e storia pulita | **assorbito**: la storia pulita è la proiezione del § 3.1; resta il tetto dei dati del turno |
| 7 Nomi delle regole | le chiusure delle proposte e delle conversazioni hanno già il nome nell'evento |
| 8 Rimozione dei lessici | invariato |

**Ordine dopo questo progetto**: 1-bis → 2 (consenso unico, in ombra sul fold) → 3 (ridotto) → 5 →
4 → 7 → 8.

## 8. Piano a passi

Interruttore unico `eventi: spento | ombra | attivo` (predefinito `ombra` dal passo 1). Ogni passo
porta le sue guardie (§ 10) e le sue prove, nell'hook e in `--completo`.

| Passo | Cosa | Prove e guardie | Ritorno | Stima |
|---|---|---|---|---|
| 0 | **Misura di oggi**: i contatori `parlato_diverso` e `domande_non_registrate` calcolati sul codice di oggi (da `played`, dalla storia e dalle frasi dette), una settimana di base sulla DGX | prova dei contatori su un giro sintetico | — | 0,5 g |
| 1 | **Registro in ombra**: `calliope/eventi/` (tipi, registro in memoria, tabella `eventi`, rotazione), scritto accanto alla storia; la proiezione del contesto calcolata e **confrontata** con la storia di Brain a ogni turno (differenze classificate per meccanismo del § 1) | `prova_eventi_tipi`, `_proiezione`, `_pure`, `_riavvio`, `_dimentica`, `_partizione`, `_porte`; guardie: `contesto_ms`, `eventi_mb_giorno`, `dimentica_residui` | `eventi: spento` | 1 g |
| 2 | **Uscita unica**: le 48 chiamate passano da `Uscita.di` con autore e atto; `voce_fine`; risposta scritta dagli eventi | `prova_uscita_unica`; `parlato_diverso` dall'ombra | `eventi: spento` (l'uscita scrive e basta) | 1 g |
| 3 | **Contesto dagli eventi**: Brain legge i messaggi dalla proiezione; spariscono `record_*`, `_seal_private`, `_togli_*`, `correggi_storia`, `claim_at`, `_compatta_storia`; il `messages` va ai due backend (Ollama e OpenAI) come oggi | `prova_brain`, `prova_dialogo_tool`, banco d'attacco (`prova_politica` 99/99, `prova_valore`), `prova_eventi_visibilita`, `_prefisso`; prova con `llm_backend: openai`; guardie `riletti`, `cache_rotta`, prima frase | `eventi: ombra` (Brain torna alla sua storia, che l'ombra continua a tenere) | 1–1,5 g |
| 4 | **Domande come oggetti**: frasi pronte senza «?» + `in_sospeso`, la macchina rende la domanda e scrive `proposta_aperta` quando è sentita; atti della tabella § 4.2; promemoria nel blocco | `prova_domande_proposte`, `prova_stati_buchi` (1, 2, 5, 6 per costruzione), i tre giri dello sviluppo; guardia `domande_non_registrate` | un'opzione per le sole domande (`eventi_domande: false`) | 1 g |
| 5 | **Registro dei turni, archivio, riavvio** come proiezioni; `correnti` in pensione (letta una volta per migrare) | `prova_conversazioni`, `prova_corsie`, `prova_cronologia*`, `prova_turnlog`; `calliope stato --turni` identico su un registro di prova | lettura di `correnti` ancora possibile per un mese | 0,5 g |
| 6 | **Pulizia** dopo una settimana di `attivo` senza differenze: via la storia mantenuta a mano e l'ombra | `--completo`, rigioco di un giro vero | — | 0,5 g |

Totale **4,5–5 giorni**, più la settimana d'ombra fra 3 e 6. Il passo 2 della macchina a stati può
partire dopo il passo 4.

### Rischi

- **Compressione**: oggi taglia la storia in mano a Brain mentre un thread riassume; con gli eventi il
  taglio è un evento `compressione` con `fino_a`, scritto sul thread della voce come oggi
  (`applica`). Rischio: un riassunto applicato su eventi cambiati nel frattempo; difesa: il lavoro
  porta il `seq` del taglio (oggi l'identità dell'oggetto `taglio`).
- **Conversazioni per persona e satelliti insieme**: oggi `RegistroConversazioni.occupa` dà la
  conversazione a una corsia per turno; gli annunci arrivano da altri thread. Con gli eventi il lock
  è per conversazione e il `seq` lo assegna il registro (§ 11.7).
- **Canale scritto**: `detto_calliope.canale` (voce, scritto, muta); per lo scritto «sentito» vuol
  dire «mandato allo schermo», e la proiezione lo tratta come detto.
- **Backend OpenAI di ripiego**: la proiezione produce gli stessi dizionari di oggi (`role`,
  `content`, `tool_calls`, `tool_call_id`, `images`); `_openai` e `_native` non cambiano. Prova di
  ogni passo con tutti e due.
- **Windows su ARM**: solo Python e `sqlite3` della libreria standard; nessuna dipendenza nuova.
- **Dimensione**: una conversazione lunga ha più eventi che messaggi (una per frase); tetto e
  rotazione nel § 10.3.
- **Due fonti durante la migrazione**: nei passi 1–2 la storia di Brain resta la fonte e gli eventi
  sono l'ombra; dal passo 3 il contrario; mai due fonti che decidono insieme.

## 9. Alternative considerate

- **Versione incrementale** (un'uscita unica che aggiunge alla storia ciò che è stato detto; Brain
  continua a mantenere la storia; il registro dei turni resta una copia): ~1 giorno. Scartata da
  Dario il 10/10: chiude il sintomo («detto = storia») ma lascia tre copie mantenute a mano, la
  trentina di punti che modificano la storia, la ricostruzione manuale per il rigioco e la macchina a
  stati che legge stati sparsi; ogni funzione nuova ne aggiunge un'altra.
- **Solo il modello parla** (nessuna frase fissa: i tool danno dati e il modello li dice): coerenza
  piena senza atti, ma +1 s circa su ogni turno con una frase pronta (la seconda passata che le frasi
  pronte evitano dal 27/09), e i testi che **devono** essere fissi (protezione dei minori con il
  numero, frase di sfida, domande della politica, cortesia senza modello) non lo possono essere.
  Scartata.
- **Una libreria o un framework di event sourcing**, o un registro esterno: dipendenze in più (ARM),
  servizi da far girare; il bisogno è una lista per conversazione e una tabella SQLite.
- **Il registro dei turni come fonte** (allungarlo con tutti gli eventi): ha la privacy e la tenuta
  sbagliate (riga per turno, niente testo degli ospiti, 30 giorni); resta una proiezione.

## 10. Costi e guardie

*Aggiunta di Dario del 10/10: ogni costo della versione forte ha una guardia misurabile e un posto
dove si vede.*

| Costo | Guardia | Dove si vede |
|---|---|---|
| 1. «Dimentica» e privacy | cancellazione vera (righe, `secure_delete`, checkpoint del WAL) per persona e conversazione; prova che cerca la frase nei byte dei file | `calliope stato`: riga «dimentica: N richieste, residui 0» da un controllo periodico (ricerca degli id dimenticati nella tabella `eventi` e nelle proiezioni su disco) |
| 2. Proiezioni semplici e veloci | funzioni pure (prova AST e di determinismo); `contesto_ms` per turno nel registro, avviso oltre 20 ms; **tetto** di 600 righe per `proiezioni.py` (prova che fallisce oltre: si alza solo scrivendo il motivo qui) | `calliope stato --turni`, accanto all'avviso della latenza |
| 3. Crescita del registro | byte per giorno e per persona; rotazione a `eventi_giorni` (7) nella forma dell'archivio; avviso oltre `eventi_avviso_mb` (proposta: 50 MB al giorno o 500 MB in tutto) | `calliope stato --eventi` e la riga nel cruscotto |
| 4. Astrazione in più | la ricetta qui sotto; prova che ogni tipo ha la sua riga di proiezione o è escluso con il motivo | prova nell'hook |
| 5. Cache del prefisso | `riletti` = token riletti dal motore per turno (`prompt_eval_count` di Ollama, `token_cache_vllm` per vLLM) sul totale; `cache_rotta` quando si rilegge oltre il turno n-2 senza compressione né cambio di profilo o modalità; avviso se la mediana dei riletti supera di metà quella del passo 0 | `calliope stato --turni` |

**Come aggiungere un tipo di evento** (ricetta, da copiare nel documento d'area al passo 1):
1. il tipo e i suoi campi in `eventi/tipi.py`, con la visibilità predefinita;
2. la riga in `PROIEZIONE_CONTESTO` (come si rende, o `ESCLUSO` e perché) e nel registro dei turni;
3. chi lo scrive: un solo punto, attraverso il registro (mai una lista a mano);
4. una prova nella famiglia `prova_eventi_*` e la riga in `prove/elenco.md`.

**Come aggiungere una proiezione**: una funzione pura in `proiezioni.py` (o un modulo accanto, se
supera il tetto) che legge solo eventi e configurazione; una prova di determinismo; se va su disco,
la sua voce in «dimentica».

## 11. Cosa oggi funziona perché le copie sono separate

*Domanda di Dario del 10/10. Ogni punto verificato sul codice; per ognuno come il registro lo
conserva in modo esplicito e con quale prova.*

1. **Isolamento di sicurezza per costruzione.** Oggi la frase di sfida (`SpeakerContext.sfida`), i
   codici di abbinamento (`last_secrets`, `redact`), i dati del turno (`memory` in `with_memory`), le
   spinte (`tail`) non entrano nella storia perché nessuno ce li scrive; i dati non fidati entrano in
   busta (`_allega_dati`, `provenienza`) e i risultati web escono a fine risposta (`WEB_TOLTO`); i
   riservati si sigillano. Con una fonte unica questo diventa un **filtro**, e un difetto del filtro
   è una fuga. Conservato così: la **visibilità** è un campo dell'evento deciso **alla scrittura**
   dal tipo e dal tool (`modello`, `turno`, `schermo`, `registro`, `mai`), non dalla proiezione; la
   proiezione del modello ammette per costruzione solo `modello` e, nel loro turno, `turno`; le
   parole della sfida e i segreti non si scrivono nemmeno nei `dati` su disco. Prove:
   `prova_eventi_visibilita` con il banco d'attacco di `prova_politica` (99) e i 27 attacchi del passo
   1 rigiocati come eventi, più un controllo per ogni turno in ombra (`fughe_proiezione`).
2. **Isolamento tra persone e conversazioni.** Oggi strutture separate (`RegistroConversazioni`,
   `ospite:<corsia>`, `occupa`). Conservato **per costruzione**: un registro per conversazione
   (precisazione di Dario del 10/10), partizionato anche su disco, nessuna API che legga «tutti gli
   eventi»; ciò che attraversa le conversazioni passa dalle porte del § 2.5. Prova
   `prova_eventi_partizione` (adulto, minore e ospite di fantasia su due satelliti), con i casi del
   passo 0 (coda all'ospite, proposta intestata a un altro).
3. **Testo per la voce diverso dal testo mostrato.** Verificato: `pronuncia.py` cambia solo il testo
   dato a Piper dentro `Speaker._pcm`; `played`, schermi e storia restano uguali. Conservato:
   `detto_calliope.testo` è quello mandato a `say`, prima della pronuncia. In più, le
   trasformazioni di `_frase_da_dire` (nomi dei tool, simboli) oggi non arrivano alla storia: con
   gli eventi il modello vede la frase detta, e la sua frase originale resta in `passata_modello`
   (vis `registro`). Prova: «apri il file» detto, «file» nell'evento e nella proiezione.
4. **Risposta interrotta.** Verificato: oggi il modello **non** tiene la risposta intera, perché
   `record_interruption` sostituisce l'ultimo messaggio con le sole frasi intere più « …
   (interrotta)»; «ripeti il secondo punto» dopo un'interruzione non trova il secondo punto già
   oggi. Con gli eventi c'è di meglio: il **previsto** resta (`detto_calliope` inviati oltre
   `voce_fine.sentite` e la `passata_modello`), il **detto** va nella storia con il segno
   d'interruzione, e il blocco dello stato del turno dopo può dire, come promemoria non parlato,
   «la risposta di prima è stata interrotta dopo: … ; non detto: …» (tetto di caratteri). Da
   decidere con Dario se accenderlo; prova con «ripeti il secondo punto».
5. **Guasti isolati.** Oggi `TurnLog.write` non solleva mai, e l'archivio scrive in un thread che
   non ferma la voce. Conservato: la fonte del processo è **in memoria**; il disco è una copia a
   lotti nel thread dell'archivio; un errore di scrittura si conta e si dice nel log come oggi
   (`errori`), la conversazione continua; al riavvio una riga troncata o un JSON rovinato chiude il
   rigioco di **quella** conversazione all'ultimo evento buono (con la regola `eventi_troncati`),
   mai l'avvio. Prova `prova_eventi_riavvio` con il file troncato e con il disco in sola lettura.
6. **Latenza.** Oggi lo streaming non aspetta il disco. Conservato: nessuna scrittura su disco nel
   percorso della prima frase (§ 5); prova a secco che `Uscita.di` non apre file né database
   (finto registro che solleva se lo fa).
7. **Concorrenza.** Oggi più corsie insieme, annunci dal thread del ciclo, lavori dell'agente da un
   altro thread (che mettono in coda, non scrivono la storia), compressione in secondo piano.
   Conservato: un lock **per conversazione**; il `seq` lo assegna il registro sotto il lock; i
   thread fuori dal ciclo (agenti, estensioni, installazioni) non scrivono eventi: mettono in coda
   come oggi, e l'evento lo scrive la corsia che lo dice; la compressione scrive il suo evento sul
   thread della voce (`applica`). Prova con due corsie e un annuncio insieme, ordine e assenza di
   buchi nei `seq`.
8. **Migrazione.** Conversazioni in corso al primo avvio: si importano da `correnti` come eventi
   sintetici (un `detto_persona`/`detto_calliope` per messaggio, `migrato: true`), poi `correnti`
   non si scrive più; l'**archivio** (`turni`) resta com'è e continua a ricevere i turni; le
   **compressioni già fatte** diventano un evento `compressione` con il riassunto salvato; il
   **backend OpenAI** riceve gli stessi messaggi di oggi (§ 8, rischi). Prova di migrazione su una
   `correnti` di prova.
9. **Foto e allegati solo in memoria** (trovato sul codice: `Conversazione.album`, `allegati`, mai
   in `esporta`). Conservato: gli eventi tengono un riferimento in memoria e su disco solo «foto,
   1280×960» o «pdf, 240 kB», come l'archivio. Prova nei byte del file.
10. **Provenienza e contaminazione** (trovato: `_prov` sul messaggio della persona, `_fonte` sugli
    annunci, `Conversazione.esterni` solo in memoria). Conservato: campi dell'evento; la
    contaminazione della conversazione è un fold degli eventi (`fonte` e `non_fidato`), e i testi
    esterni restano in memoria come oggi. Prova: `prova_politica` sulla provenienza dopo il
    riavvio (oggi `esterni` si perde: con gli eventi la **traccia** resta, il testo no).
11. **Il registro dei turni senza testo per gli ospiti e per i minori fermati** (verificato in
    `TurnLog.write` e `_registra_controlli`). Conservato come proiezione con le stesse regole; prova
    che confronta il registro di oggi e quello proiettato su un giro sintetico.

## 12. Documentazione da aggiornare quando si fanno i passi

- [`voce-e-regole`](../aree/voce-e-regole.md): una sezione «Il registro degli eventi» (tipi, uscita
  unica, atti di dialogo, la ricetta del § 10).
- [`contesto-conversazione`](../aree/contesto-conversazione.md): la storia come proiezione, le due
  forme dei turni, la cache, la rotazione.
- [`sicurezza-politica`](../aree/sicurezza-politica.md): la visibilità per evento.
- [`architettura.md`](../architettura.md) § 3 e § 4, [`architettura-tool.md`](../architettura-tool.md)
  (frasi pronte senza domanda, `in_sospeso`).
- `CLAUDE.md`: una riga nella tabella dell'architettura (`calliope/eventi/`).

## Fonti

- [`2026-10-10-macchina-stati.md`](2026-10-10-macchina-stati.md) § 3, § 6, § 9, § 10
- Decisione [0027](../decisioni/0027-conversazione-come-registro-di-eventi.md); [0022](../decisioni/0022-macchina-a-stati-del-dialogo.md), [0007](../decisioni/0007-streaming-e-latenza.md), [0014](../decisioni/0014-politica-unica-dati-in-busta.md)
- Il giro del 10/10 alle 07:11–07:21 (registro della DGX, cartella temporanea della sessione)
