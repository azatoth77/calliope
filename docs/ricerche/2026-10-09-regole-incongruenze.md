# Regole di Calliope: incongruenze e sovrapposizioni (09/10/2026)

*Analisi del 9 ottobre 2026 sera, chiesta da chi amministra: «fai un giro di analisi delle regole
per trovare eventuali incongruenze o sovrapposizioni che potrebbero generarne altre». È stata
fatta sul codice di `main` a 141e2f8 (sicurezza per valore accesa, fase 4) e sul registro dei
turni della DGX dal 02 al 09/10. Dal registro sono stati letti solo i campi senza testo: `regole`,
`esito`, `livello`, nomi e `ok` dei tool, `politica_ombra` senza valori, tipo della conversazione.
Gli script di misura non sono nel repository (cartella temporanea della sessione): uno estrae i
campi, gli altri contano frequenze, coppie e sequenze e passano le stesse frasi da tutte le
regole del sì e del no. Nessuna modifica al codice. Tre lavori della stessa sera toccano il
codice (politica, valore e strumenti; ricerca; voce e conversazione): dove una proposta li
incrocia è indicato.*

## In breve

Le regole sono tante: **276 nomi** scritti nel codice, più una trentina composti al volo
(`politica_*`, `valore_*`, `analisi_*`, `uscita_*`). Nei 1437 turni del registro ne sono scattati
132; 180 non sono mai scattate, e di queste circa 90 esistevano già prima del 07/10. Prese una per
una sono quasi tutte ragionevoli. I problemi nascono dove più regole guardano lo stesso ingresso
con criteri diversi. Le dieci incongruenze più importanti, in ordine:

1. **«Questo sì basta?» si decide in sei punti con sei criteri diversi** (§ 3.1): `conferma_voce`
   della politica, `admin_confermato` e `conferma_breve` nel registro dei tool, la zona grigia
   accettata dalla memoria dell'intento, il `cv` della modalità sviluppo, il livello in
   `ToolRegistry.call`, e da stasera `consenso_della_persona` del ramo della politica. La
   causa vera di tutte le sfide del registro è questa, non i dati: **6 `politica_sfida` su 6
   sono arrivate con la voce di chi amministra scesa a «familiare»**. Nel 22 % dei passaggi
   entro un minuto sullo stesso satellite chi amministra scende a familiare.
2. **Il «sì» a una domanda della politica per valore lo giudica la politica di prima**
   (`valore.decidi_valore` restituisce `base` sul consenso, § 3.2). È il caso della luce delle
   20:39: la domanda nasce da `valore_non_ancorata`, il «Sì» finisce in `politica_sfida` e il
   motivo detto è «c'è di mezzo una pagina internet». Il ramo `sera-politica-strumenti` lo
   corregge per E1–E2 (`valore_consenso_breve`). Restano E3 e il motivo sbagliato.
3. **Il motivo detto è la prima fonte in ordine alfabetico** (`sorted(t.contaminazione)[0]`).
   Non è la fonte del valore né la ragione della domanda; anche ««X» viene da…» della politica
   per valore usa quella fonte (§ 3.3).
4. **Il campo `politica_ombra` non si aggiorna dopo le correzioni a valle** (modalità sviluppo,
   domanda già fatta, persona non riconosciuta): 4 chiamate eseguite il 09/10 risultano
   «rifiuta» o «conferma». Falsa proprio la misura che si guarda sulla DGX (attrito, «ESEGUITE
   con un bersaglio dal dato», § 3.4).
5. **Sei lessici del sì e del no che non coincidono** (§ 3.5): «No, mi va bene» non è né consenso
   né rifiuto, ma chiude la memoria dell'intento. «Sì, però fallo dopo» è un consenso, e così
   «Si chiama Marco» (il «si» impersonale). «Sì, non c'è problema» non è un consenso.
6. **Uscite, stop e cortesia vengono prima della proposta in sospeso** (§ 3.6): «Sì, puoi andare»
   dopo «Lo apro?» addormenta Calliope, e «Calliope, ok» detto interrompendo la domanda è uno
   stop.
7. **La spinta dell'ultimo giro resta nella passata finale** (difetto, § 3.7): «richiamalo
   adesso» e «non richiamarlo» nello stesso prompt; se il modello scrive una chiamata come
   testo, la risposta resta vuota.
8. **Fase 4: due regressioni di sicurezza o di attrito** nate dal passaggio alla nuova
   politica (§ 3.8). `installa_avvia` ha la sfida nella politica di prima, ma è E3: con la voce
   riconosciuta ora esegue senza sfida. La rinomina detta per intero (`politica_valore_detto`)
   torna a chiedere.
9. **Stesso nome di regola per esiti diversi** (`valore_non_ancorata` rifiuta o chiede,
   `politica_azione_non_chiesta` tre esiti, `voce_incerta_chiede` tre punti, `compagnia_nome`
   due significati e due turni, `intento_chiuso` due cause): il registro non distingue (§ 3.9).
10. **Dati del turno che si contraddicono e si sommano** (§ 3.10). Ricerca recente e archivio
    («cerca ancora» contro «di' che non lo sai»), estensione nominata e ricerca, riferimento
    della casa e rifiuto sullo stesso tool. Nel caso peggiore oltre 6000 caratteri prima della
    frase.

Seguono, più in basso: conversazione e «altra persona» con cinque definizioni (§ 3.11), tempi
diversi per lo stesso concetto (§ 3.12), la domanda dello sviluppo che fa perdere la proposta
(§ 3.13), due domande nella stessa risposta (§ 3.14), il guardiano dei minori dopo i tool (§
3.15) e parametri senza effetto (§ 3.16). Il principio 10 è nel § 4, cosa fare nel § 5.

## 1. Inventario: dove si decide, in che ordine

### 1.1 La catena di un turno

L'ordine conta: chi viene prima decide, e chi viene dopo non vede più l'ingresso.

| # | Fase | Dove | Regole (nome nel registro) |
|---|---|---|---|
| 1 | Identità della voce, compagnia | `ciclo._chi_parla` | `voce_margine`, `voce_continuita`, `minore_piu_protetto`, `amministra_minore_vicino`, `compagnia_senza_breve`, `voci_compagnia` |
| 2 | Più voci senza nome | `ciclo._compagnia_senza_nome` | `compagnia_nome` |
| 3 | Conversazione del turno | `ciclo._conversazione_del_turno`, `corsie.scegli` | `voce_incerta_chiede`, `doppione_altro_satellite` |
| 4 | Arruolamento, nome vero | `ciclo._arruolamento`, `_nome_reale` | `uscita_*`, `arruolamento_senza_nome`, `nome_detto` (annullamenti senza nome) |
| 5 | Richiamo, interruzione | `ciclo._richiamo`, `_dopo_interruzione` | `stop_interruzione`, `cortesia_dopo_nome`, `wake_fuori_posizione`, `nome_da_solo_*` |
| 6 | Uscite | `ciclo._uscite` | `uscita_spegni`, `uscita_dormi`, `uscita_spegni_satellite`, `nuova_conversazione` |
| 7 | Chiusure | `ciclo._chiusure` | `cortesia`, `stop`, `cortesia_dopo_domanda` (solo senza proposta in sospeso) |
| 8 | Cancelli dei minori | `ciclo._secondo_cancello`, `_fuori_orario` | `pericolo_*`, `minore_fuori_orario` |
| 9 | Contesto e allegati | `ciclo._contesto_e_allegati` | `approfondisci`, `immagine_in_ingresso`, `foto_davanti` |
| 10 | Brain, prima del modello | `brain.stream_reply` | `sospeso_altrui_consenso`; `conversazione_altra_persona`, `conversazione_scaduta`; `conversazione_ripresa`; `sospeso_altra_persona`, `sospeso_altro_satellite`; `proposta_rifiutata`; `intento_chiuso`; `azione_in_sospeso` e le annotazioni `consenso_forma_chiusa`, `consenso_in_coda`, `consenso_avversativo`; `sfida_risposta` |
| 11 | Dati del turno | `brain._reply` | `tono_persona`, `minore_preset`, `riferimento_casa`, `riferimento_agenda`, `riferimento_lavoro`, `ricerca_recente`, `estensione_nominata`, `estensioni_elenco_turno`, `sviluppo_modalita`, `rifiuto_nei_dati`, `storia_tagliata` |
| 12 | Giri del modello | `brain._reply`, `_turn` | `correzione_tool`, `correzioni_esaurite`, `spinta_*`, `dichiarata_*`, `vuoto_seconda_passata`, `textcallguard`, `chiamata_in_mezzo`, `eco_contesto` |
| 13 | Ogni tool | `ToolRegistry.call` → `politica.controlla` | vedi § 1.2 |
| 14 | Dopo il testo | `riferire.filtra` → `guardia.filtra` → `_solo_se_rivolta` | `uscita_istruzione`, `uscita_segreti`, `guardiano_*`, `non_rivolta*` |

### 1.2 Ogni chiamata a un tool

`ToolRegistry.call` (`tools/registry.py` 195–338) fa i controlli in quest'ordine:

1. nome vecchio o storpiato (`tool_nome_vecchio`, `tool_nome_corretto`);
2. `politica.bloccata` (`web_azione_bloccata`, `dopo_dato_valore_detto`), **prima del livello**;
3. `bersaglio_assente`, `incoerente`;
4. **`conferma_breve`**: un «sì» breve al tool proposto, `admin_confermato`, alza il livello ad amministra (riga 241);
5. **`compagnia_voce_nella_frase`**: in compagnia, una frase breve abbassa il livello a ospite (riga 250);
6. **livello**: per chi amministra con una frase breve o in zona grigia, la frase di sfida; voce incerta con un minore: «chi parla?»; scritto: `scritto_serve_voce`; altrimenti `permesso_livello`;
7. `minori.permesso`;
8. schema degli argomenti (`tool_argomenti_mancanti`, `tool_argomenti_non_validi`);
9. `politica.controlla`.

`politica.controlla` (`politica.py` 1805–1933) prosegue così:

1. **`_gia_rifiutata`** → `politica_proposta_rifiutata` o `rifiuto_superato`;
2. `cv = conferma_voce`, `vf = voce_frase`, **`intento_aperto`**;
3. **con dati non fidati nella storia**: tutte e due le politiche. Con `politica_per_valore` vale la nuova (`decidi_valore`); senza dati vale solo `decidi`;
4. **modalità sviluppo**: con `cv` e un passo interno, una domanda o un rifiuto delle regole in `SVILUPPO_SALTA` diventa `sviluppo_intento` o `sviluppo_senza_domanda`;
5. la resa dell'esito: blocco, rifiuto leggero, `politica_domanda_non_ripetuta` (solo per «conferma»), vieta, sfida (con il prefisso «C'è di mezzo…»), domanda con `in_sospeso`.

**`politica.decidi` (la politica di prima), in ordine:**

- vietato;
- `web_azione_bloccata` (doppione del punto 2 qui sopra);
- sicuro, `_lettura_che_esce`, `sola_lettura`;
- `politica_valore_detto`;
- innocua;
- **`intento_confermato`**.
- *Conversazione pulita*: domanda della politica in sospeso, poi `politica_azione_non_chiesta`, `politica_cancellazione_non_chiesta`, `politica_cambio_non_chiesto`, infine ACCETTATA o ESEGUI.
- *Conversazione contaminata*:
  - `richiesta_ripetuta`, `politica_delega`, `politica_argomento_esterno`, `politica_documento_proprio`;
  - classe AZIONE: `consenso_richiesta`, `politica_fatto_detto`, `politica_azione_non_chiesta` (prima rifiuta, poi chiede), `politica_azione_non_giustificata`, `politica_argomento_non_detto`;
  - classe PERICOLOSO: al «sì» con le stesse chiavi, `politica_conferma` se il modello ha cambiato altri argomenti, ESEGUI con `cv`, **`politica_sfida` senza `cv`**; poi `politica_richiesta_voce`, `politica_sfida` (`cl.sfida`), `politica_conferma`.

**`valore.decidi_valore` (la politica per valore, accesa), in ordine:**

- **passa a `base`, cioè alla politica di prima**: conversazione pulita, letture, vietati, blocchi, delega, intento, `consenso_richiesta`, `fatto_detto`, sola lettura, innocua e **ogni «sì» alla proposta di questo tool** (`consenso_turno`);
- poi `valore_lettura` (E0);
- **`valore_non_ancorata`**: rifiuta la prima volta nella risposta, poi chiede;
- `valore_bersaglio_dato`, `valore_contenuto_dato`, `valore_contenuto_non_detto`, `valore_dati_personali`;
- `valore_e4_sfida`, `valore_voce` (E3 con la voce in questa frase), `valore_e3_chiede`, `valore_esegue`.

### 1.3 Il testo della persona: chi lo guarda

| Lessico o funzione | File | Forma | Effetto |
|---|---|---|---|
| `_EXIT_LEAD` + `_SHUTDOWN` / `_SLEEP` | `wakeword.py` 206–264 | chiusa (con la sola prima clausola per «dormi») | esce o dorme, prima di Brain |
| `_NUOVA` | `wakeword.py` 334 | chiusa | `nuova_conversazione` |
| `_CLOSING`, `_SILENCE`, `_THANKS` | `wakeword.py` 360–383 | chiusa | `is_stop` (dopo un'interruzione, **senza guardare la proposta**), `closing_kind` (cortesia, solo senza proposta) |
| `_SI`, `_NO`, `FORME_SI`, `TESTA_SI` | `politica.py` 680–790 | `_SI` tra le prime 4 parole di un pezzo; **`_NO` ovunque nella frase** | `consenso` |
| `_RIFIUTO_TESTA`, `_CORREZIONE` | `politica.py` 786–830 | chiusa in testa, eccezioni cercate nel resto | `rifiuto` → `proposta_rifiutata` |
| `valore.ANNULLA` | `valore.py` 261 | «no» e «annulla» **in testa senza eccezioni**; basta, niente, stop per intero | `intento_chiuso` |
| `re.match("\W*(annulla\|basta\|stop\|lascia stare)\b")` | `ciclo.py` 1804 | prefisso | annulla l'arruolamento, **senza regola** |
| `re.match("\b(no\|non\|nessuno\|basta)\b")` | `ciclo.py` 1893 | prefisso | rifiuta il nome vero, **senza regola** |
| `ACTION_REQUEST`, `_INTERNE` | `sicurezza.py` 90, `politica.py` 658 | dentro la frase (di proposito) | `chiesta_azione`, ancoraggio della politica di prima |
| `verbi` dei tool con `_NEGATO` | `politica.py` 392–510, 1403 | dentro la frase, negazione controllata | `chiesto_con_verbi`, `ancorata` |
| `OFFERTA`, `chiede_risposta` | `brain.py` 350–364 | sul testo **di Calliope** | la cortesia non risponde a un'offerta |

## 2. Cosa dice il registro (02–09/10)

1437 turni, 1093 con almeno una regola. Livelli: amministra 1002, familiare 239, ospite 160.

### 2.1 Frequenza (turni in cui la regola compare)

| Regola | Turni | Note |
|---|---|---|
| `tono_persona` | 895 | dato del turno quasi fisso (dal 04/10) |
| `azione_in_sospeso` | 161 | 107 amministra, **54 familiare** |
| `sviluppo_modalita` | 149 | 130 l'08/10 |
| `sviluppo_intento` | 64 | domande saltate nello sviluppo |
| `conversazione_ripresa` | 61 | |
| `riferimento_casa` / `riferimento_agenda` | 57 / 43 | |
| `politica_conferma_unica` | 54 | |
| `sviluppo_collaudo` + `sviluppo_collauda` | 49 + 43 | stessa chiamata, due nomi (43 volte insieme) |
| `estensioni_elenco_turno` | 47 | |
| `politica_conferma` | 37 | 26 il 07/10, 2 il 09/10 |
| `conferma_breve` | 34 | **34 su 34 a livello familiare** |
| `ricerca_recente` | 33 | solo il 09/10 |
| `conversazione_scaduta` | 28 | sottostimata: 2 delle 3 vie di chiusura non la scrivono |
| `minore_preset` | 28 | |
| `cortesia` | 26 | **20 su 26 a livello familiare** |
| `conversazione_altra_persona` | 25 | 18 prima del 06/10, poi una al giorno, solo nella conversazione anonima |
| `sfida_voce` / `sfida_risposta` | 22 / 16 | `sfida_voce`: 14 familiare, 8 amministra |
| `stop` / `stop_interruzione` | 21 / 16 | |
| `politica_sfida` | 6 | **6 su 6 con chi amministra sceso a familiare** |
| `valore_esegue` / `valore_voce` / `valore_non_ancorata` | 8 / 3 / 2 | dalla sera del 09/10 |
| `intento_chiuso` / `intento_confermato` | 4 / 3 | |
| `proposta_rifiutata` | 2 | dal 09/10 |

**Mai scattate** (180), tra le più vecchie:
- `spinta_archivio`, `ricerca_promessa`, `quarantena`, `storia_tagliata`, `stt_capito`;
- `politica_azione_incoerente`, `politica_bersaglio_assente`, `cortesia_dopo_nome`, `wake_fuori_posizione`;
- `consenso_forma_chiusa` (dal 07/10), `consenso_in_coda` e `politica_domanda_non_ripetuta` (dall'08/10).

Le altre sono dell'08–09/10 (minori, compagnia, correzioni dei tool) e non hanno ancora avuto
occasione. Le date di nascita vengono da `git log -S`: la storia prima del 06/10 è riscritta,
quindi «06/10» vuol dire «fino al 06/10».

### 2.2 Coppie e sequenze che dicono qualcosa

- `azione_in_sospeso` → `azione_in_sospeso` nel turno dopo: **73 volte**. Le domande si
  incatenano.
- Nello stesso turno di un `azione_in_sospeso` arriva una nuova domanda della politica 74 volte
  su 161: `politica_conferma_unica` 46, `politica_conferma` 18, `politica_sfida` 6,
  `valore_voce` 2, altre 2.
- `sfida_voce` → `sfida_risposta` 14, `sfida_voce` → `politica_conferma_unica` 13: la sfida
  passa quasi sempre, quindi costa un turno ma non ferma nessuno.
- `politica_conferma` → `azione_in_sospeso` 37, poi → `politica_conferma_unica` 21.
- **Passaggi di livello entro 60 s sullo stesso satellite**:

  | da \ a | amministra | familiare | ospite |
  |---|---|---|---|
  | amministra | 490 | **142** | 15 |
  | familiare | 109 | 35 | 10 |
  | ospite | 39 | 5 | 30 |

  Le frasi brevi («sì», «grazie») fanno scendere chi amministra, e su quell'ingresso lavorano
  tutte le regole del consenso.
- **Doppie chiamate dello stesso tool nella stessa risposta**: 17. `sviluppo_collauda` 5,
  `web_cerca` 3, `data_calcola` 2, altre 7.
- **Ombra** (fase 3 e 4): la vecchia chiedeva e la nuova rifiuta per `valore_non_ancorata` in
  29 chiamate (24 in ombra, 5 accese). In 28 la vecchia chiedeva e la nuova eseguiva
  (`valore_voce`).

## 3. Incongruenze e sovrapposizioni

Per ognuna: esempio (vero dal registro o costruito con nomi di fantasia), rischio, proposta,
priorità (P1 subito, P2 dopo, P3 da documentare o quando si tocca). «In corso» indica che uno dei
tre rami della sera ci sta già lavorando.

### 3.1 «Questo sì basta?» in sei punti — P1

**Cosa.** La stessa domanda, «la frase di questo turno basta per confermare un'azione di questa
persona?», ha sei risposte:

| Punto | Criterio |
|---|---|
| `conferme.admin_confermato` (registro, `conferma_breve`) | voce ad amministra, sfida superata, o «breve» con `SpeakerContext.conferma_breve` |
| `politica.conferma_voce` | voce con un nome a qualunque livello, sfida, `admin_confermato`, o «breve» con `voce_sicura` e punteggio ≥ 0,40 |
| `valore.intento_aperto` | voce, breve **e zona grigia** («conversazione»), entro 600 s |
| `politica.voce_frase` | voce sopra soglia in questa frase |
| livello in `ToolRegistry.call` | amministra o sfida (righe 264–285); in compagnia una frase breve vale ospite |
| `valore.consenso_della_persona` (ramo `sera-politica-strumenti`, in corso) | `identified_by` voce o breve, con un nome |

**Esempio vero (09/10, 20:39).** Chi amministra dice «Sì» a «vuoi che spenga la luce…?». È una
frase breve, e scende a familiare. `conferma_voce` è falso, quindi `politica_sfida`. Nello stesso
turno sarebbe stato vero `intento_aperto`, se ci fosse stata un'intenzione. Il ramo della sera
aggiunge un settimo criterio per E1–E2.

**Rischio.** Un «sì» passa o non passa secondo il ramo che lo guarda. Ogni correzione aggiunge
un criterio invece di toglierne. Nel registro la sfida della politica nasce sempre dalla voce
(6 su 6), mai dal dato.

**Proposta.** Una sola funzione, per esempio `conferme.basta(ctx, effetto, classe) → "ok" |
"sfida" | "chi_parla" | "no"`, che dica per ogni effetto (E1–E4) e per ogni modo di
riconoscimento (voce, breve, zona grigia, scritto, compagnia) se basta. Tutti e sei i punti la
chiamano, e la sua tabella è il solo posto da tarare. Va fatta **dopo** l'unione del ramo
`sera-politica-strumenti`, partendo dal suo `consenso_della_persona`.

### 3.2 Il «sì» alla domanda della politica nuova lo giudica quella di prima — P1 (in corso per E1–E2)

**Cosa.** In `decidi_valore` (`valore.py` 554) un consenso alla proposta restituisce `base`,
cioè `politica.decidi`. La domanda però l'ha fatta la politica per valore: `valore_non_ancorata`
o `valore_e3_chiede`. La risposta passa allora dalla regola di prima: «pericolosa con dati di
mezzo → serve la voce» (`politica.py` 1612–1616).

**Esempio vero.** Ecco la sequenza delle 20:39 come la mostra il registro:

| Ora | Livello | Regole | Tool (ombra) |
|---|---|---|---|
| 20:39:05 | amministra | `valore_non_ancorata` ×2 | `casa_comando` rifiuta, poi `casa_comando` conferma |
| 20:39:17 | familiare | `azione_in_sospeso`, `politica_sfida`, `sfida_voce` | vera = nuova = sfida |
| 20:39:28 | amministra | `sfida_risposta`, `politica_conferma_unica` | eseguita |

Per spegnere una luce sono serviti 4 turni, con un motivo che parla di una pagina internet.

**Proposta.** Il ramo della sera esegue per E1–E2 con `valore_consenso_breve`. Dopo l'unione
servono due cose:
- il consenso a una domanda della nuova va giudicato dalla nuova anche per E3, cioè `valore_voce`
  con il criterio del § 3.1 e la sfida solo per E4 o `cl.sfida`;
- `politica_conferma_unica` va scritta in base a chi ha fatto la domanda.

### 3.3 Il motivo detto: la prima fonte in ordine alfabetico — P1 (piccola)

**Cosa.** `fonte = sorted(t.contaminazione)[0]` (`politica.py` 1547, `valore.py` 557). È la fonte
detta in «C'è di mezzo…», nel prefisso della sfida e in ««X» viene da…» della politica per valore
(`valore_bersaglio_dato`, `valore_contenuto_dato`). La politica di prima, per l'argomento
esterno, usa invece la fonte vera del valore (`prov.esterne`, 1564–1569).

**Esempio costruito.** Nella conversazione ci sono una foto e una ricerca web. «Il numero 0471…»
viene dalla pagina, ma Calliope dice «viene da una foto, non da te». Con un lavoro dell'agente e
una ricerca dice sempre «il lavoro di un agente».

**Rischio.** La persona riceve una spiegazione falsa e non capisce perché le si chiede. Per la
luce (§ 3.2) il motivo non c'entrava niente: la causa era la voce.

**Proposta.**
- In `decidi_valore`, la fonte va presa da `Fonti` per l'argomento che fa scattare la regola.
- Nel prefisso della sfida si dice la ragione vera: «non ti ho riconosciuta bene dalla voce»
  quando la causa è `cv` falso, la fonte solo quando la causa è il dato.

### 3.4 L'ombra non segue la decisione finale — P1 (misura)

**Cosa.** `politica_ombra` si scrive con l'esito di `decidi_valore` (`politica.py` 1853), prima
di tre correzioni che vengono dopo:
- il salto dello sviluppo (`sviluppo_intento`, 1866–1879);
- `politica_domanda_non_ripetuta` (1905);
- la frase per chi non è riconosciuto (1920).

**Dal registro (09/10).** Quattro chiamate con `attiva: true` sono state eseguite (`ok`) mentre
l'ombra dice rifiuta o conferma:
- `sviluppo_passo` alle 20:58;
- `sviluppo_collauda` alle 20:59:39 e alle 20:59:59;
- `sviluppo_passo` alle 21:00.

Tutte hanno `sviluppo_intento` nelle regole.

**Rischio.** `attrito.py` conta l'attrito e le «ESEGUITE con un bersaglio dal dato» dalla
`nuova` dell'ombra. Sono le due misure da cui dipende la decisione di tenere accesa la fase 4.

**Proposta.** Aggiungere all'ombra `finale` e `finale_regola` dopo tutte le correzioni (oppure
riscrivere `nuova` con un campo `corretta_da`), e fare contare `attrito` su `finale`. È poco
codice; la prova va in `prova_attrito`.

### 3.5 Sei lessici del sì e del no — P1

**Cosa.** Le parole del consenso e del rifiuto stanno in sei posti:
- `politica._SI`, `_NO` e `FORME_SI`;
- `politica._RIFIUTO_TESTA`;
- `valore.ANNULLA`;
- `wakeword._CLOSING`, `_SILENCE` e `_THANKS`;
- due regex senza nome in `ciclo.py` (arruolamento e nome vero).

Ognuno è nato da un caso diverso e nessuno sa degli altri. Stesse frasi, passate dal codice di
`main` (script della sessione):

| Frase (dopo «Lo apro?») | `consenso` | `rifiuto` | chiude l'intento | cortesia | stop dopo interruzione | uscita |
|---|---|---|---|---|---|---|
| «No, mi va bene» | no | no | **sì** | — | no | — |
| «No no, va bene, fallo» | no | no | **sì** | — | no | — |
| «No, aspetta, sì» | no | no | **sì** | — | no | — |
| «Sì, però fallo dopo» | **sì** | no | no | — | no | — |
| «Sì, non c'è problema» | **no** | no | no | — | no | — |
| «Sì, certo, non preoccuparti» | **no** | no | no | — | no | — |
| «Si chiama Marco» | **sì** | no | no | — | no | — |
| «Sicuro?» | **sì** | no | no | — | no | — |
| «Giusto per sapere, che ore sono?» | **sì** | no | no | — | no | — |
| «Perfetto, grazie» | sì | no | no | grazie | **sì** | — |
| «Ottimo» | **no** | no | no | conferma | sì | — |
| «Lascia la luce accesa» | no | **sì** | no | — | no | — |
| «Sì, puoi andare» | sì | no | no | — | no | **dormi** |
| «Calliope, ok» | sì | no | no | conferma | **sì** | — |

**Rischi.**
- «No, mi va bene» (assenso molto comune in italiano) chiude la memoria dell'intento, ma lascia
  la proposta viva: decide il modello e la politica richiede.
- `_NO` cerca «non», «niente», «mai» ovunque. «Sì, non c'è problema», cioè un sì pieno, non vale.
- `_SI` contiene «si», «sicuro», «giusto» e «conferma» come parole sciolte: una domanda o
  un'altra frase in testa vale come consenso, se c'è una proposta in sospeso.
- «Sì, però fallo dopo» è un consenso a farlo **adesso**.
- «Ottimo», «benissimo», «capito» sono cortesia ma non consenso.

**Proposta.** Un modulo solo, per esempio `risposte.py`, con `classifica(frase) → si | no |
correzione | cortesia | silenzio | altro` sulla forma intera, tolti riempitivi e nome. Lo usano
`consenso`, `rifiuto`, `valore.chiude`, `closing_kind` e `is_stop`, più le due regex di
`ciclo.py`, che ricevono anche un nome. Il resto della frase («però fallo dopo», «non c'è
problema») segue tre regole:
- non annulla il sì se è una forma di rinforzo («nessun problema», «non c'è problema», «non
  preoccuparti»);
- lo rimanda al modello se è un'altra richiesta;
- «no» seguito da un sì è un sì.

I casi della tabella diventano contrari in `prova_testo.py`. Va coordinato con il ramo
`sera-voce-conversazione`, se tocca il «no» che chiude.

### 3.6 Le regole prima di Brain non sanno della proposta — P2

**Cosa.** `_uscite` (fase 6) e `_dopo_interruzione` (fase 5) girano prima di Brain e non guardano
`has_pending`. `_chiusure` invece lo guarda: la cortesia non risponde se c'è una proposta.

**Esempi costruiti.**
- «Sì, puoi andare» dopo «Lo apro?»: Calliope si addormenta, e il file non si apre.
- «Calliope, ok» detto mentre lei sta ancora dicendo «…Lo apro?»: `stop_interruzione`, e il
  consenso si perde.

**Proposta.** Con una proposta in sospeso, un sì in testa (§ 3.5) va a Brain prima dell'uscita e
dello stop; l'uscita vale solo per la frase intera senza il sì. Due contrari in `prova_testo`.

### 3.7 La spinta resta nella passata finale — P1 (difetto)

**Cosa.** In `Brain._reply`, `tail` (la spinta) si azzera solo dopo un `_turn` (`brain.py`
3091). La passata finale senza tool (3366–3373) usa `with_memory(...)`, che aggiunge `tail` in
fondo. Due casi:
- **correzioni finite**: al giro *n* esce `CORREZIONE_NUDGE` («richiamalo») e `continue`; al
  giro *n+1* `_correzione_esaurita` fa `break`. La passata finale ha `CORREZIONE_ESAURITA`
  («non richiamarlo») vicino al prompt di sistema e `CORREZIONE_NUDGE` in fondo;
- **giri finiti** dopo `CLAIM_NUDGE` o `PROMISE_NUDGE` («chiama adesso il tool»): nella stessa
  passata c'è anche «Rispondi ora, senza chiamare altri tool».

Nella passata finale le chiamate si scartano, ma `TextCallGuard` è attiva: una chiamata scritta
come testo viene trattenuta e buttata, e la risposta resta vuota senza ripiego.

**Proposta.**
- `tail = []` prima della passata finale.
- Ripiego sul vuoto anche lì: `vuoto_ripiego` o la frase di `CORREZIONE_ESAURITA`.
- Una prova a secco con il modello finto che chiama sempre male.

### 3.8 Fase 4: ciò che la politica di prima faceva e la nuova no — P1

**Cosa.** La tabella del § 1.2 mostra quali regole di prima sono passate in ombra con
`politica_per_valore`. Tre non hanno un equivalente nella matrice.

1. **`installa_avvia`** ha `sfida=True` (`politica.py` 314) ma è E3 (`valore.py` 212). Con un
   dato di mezzo e la voce riconosciuta in questa frase, la nuova dà `valore_voce` ed **esegue
   senza la frase di sfida**. Prima la sfida c'era sempre. Le altre `sfida=True` sono E4 e la
   mantengono. È una regressione di sicurezza piccola ma vera.
   - **Proposta**: `cl.sfida` vale sempre, come pavimento, in `decidi_valore`; oppure
     `installa_avvia` passa a E4.
2. **`politica_valore_detto`** (rinomina detta per intero, 08/10) non è tra le regole che
   passano: la rinomina è E3, e senza `voce_frase` diventa `valore_e3_chiede`. Torna la domanda
   che l'08/10 aveva tolto.
   - **Proposta**: aggiungere la regola alla lista di quelle che passano (`valore.py` 542).
3. **`da_config`** (la città della casa, 09/10) vale come parola della persona per la vecchia,
   ma non per la nuova (`Fonti.da`).
   - **Proposta**: metterla in `Fonti.fidato`.

**Inoltre, ancora attive ma ormai doppie.**
- `consenso_turno` ricopia a mano la logica di `decidi` (1434 contro 1499–1554).
- `web_azione_bloccata` si controlla due volte (registro e `decidi`).
- Le regole della politica di prima per la conversazione contaminata (`politica_conferma`,
  `politica_azione_non_*`, `politica_argomento_*`) restano nel codice solo per l'ombra al
  contrario e per il ripiego in caso di eccezione.

Da decidere dopo una settimana di fase 4: se l'ombra al contrario non serve più, la politica di
prima si riduce a vietato, blocco, delega e intento, cioè a quello che passa comunque (P2).

### 3.9 Stesso nome, esiti diversi — P2

| Nome | Esiti o punti |
|---|---|
| `valore_non_ancorata` | rifiuta, la prima volta nella risposta; chiede, la seconda |
| `politica_azione_non_chiesta` | chiede (conversazione pulita); rifiuta o chiede (AZIONE contaminata); chiede (documento proprio) |
| `voce_incerta_chiede` | `ciclo.py` 1763 (proposta con voce incerta), `brain.py` 2289 (risposta a una sfida), `conferme.py` 292 (richiesta della sfida) |
| `compagnia_nome` | chiude la finestra d'ascolto (scritta sul **turno prima**); scarta la frase senza nome |
| `intento_chiuso` | «no/annulla»; foto o file nuovi |
| `proposta_rifiutata` | proposta rifiutata; sfida rifiutata |
| `uscita_dormi` | frase intera; solo la prima clausola |
| `sviluppo_collaudo` + `sviluppo_collauda` | stessa chiamata, due nomi (43 turni su 49 insieme) |

**Rischio.** Il registro non dice quale ramo è scattato: non si può misurare, per esempio, quanti
`valore_non_ancorata` arrivano alla persona.

**Proposta.** Un suffisso per l'esito o per il punto (`valore_non_ancorata_rifiuta` / `_chiede`,
`intento_chiuso_dato`…). Per `compagnia_nome`, scriverla sul turno giusto. Il cruscotto e
`compagnia.riassunto` raggruppano per prefisso.

### 3.10 Dati del turno che si contraddicono — P2 (ricerca in corso)

**Cosa.** I messaggi del turno sono indipendenti e si sommano: fino a 13 blocchi più una spinta.
Coppie in conflitto:

| Coppia | Il primo dice | Il secondo dice |
|---|---|---|
| `RICERCA_MSG` e `RICERCA_NUDGE` contro `ARCHIVIO_NOTA` | «chiama di nuovo web_cerca, non dire che non hai altre informazioni senza aver cercato» | «se non c'è niente di pertinente, di' che non lo sai» |
| `EST_NOMINATA_MSG` contro `RICERCA_MSG` | «chiama quel tool, non un altro (internet, biblioteca)» | «richiama la ricerca» |
| `REFERENCE_MSG` / `AGENDA_MSG` contro `RIFIUTO_MSG` (stesso tool) | «chiama subito casa_comando senza chiedere» | «non chiamare casa_comando per questo» |
| `SOSPESO_ALTRUI_MSG` contro `STT_INCERTE_MSG` | «non fare domande» | «se resta poco chiaro, chiedi» |

Dopo `conversazione_altra_persona` la storia e i riferimenti si azzerano, ma `_altrui_msg`, già
calcolato, resta. Nel caso peggiore i dati del turno superano i 6000 caratteri: i rifiuti
crescono fino a 5 (~1300), lo sviluppo vale 1250, l'elenco delle estensioni fino a 12 voci.

**Rischio.** Il modello sceglie a caso fra istruzioni opposte. La spinta in coda, che vince quasi
sempre, può essere quella sbagliata (§ 3.7).

**Proposta.**
- (a) Un ordine di precedenza scritto in `_reply`: rifiuto > riferimento dello stesso tool;
  estensione nominata > ricerca recente quando il nome dell'estensione è nella frase.
- (b) Un solo messaggio «ricerca» che decide fra internet, biblioteca e archivio (il ramo
  `sera-ricerca` sta già unendo l'elenco delle ricerche: lì si toglie anche `ARCHIVIO_NOTA`
  come messaggio separato). *Fatto il 09/10 sera (ramo `sera-ricerca`):* `RICERCA_MSG` elenca le
  ricerche con la loro fonte; con le ricerche nei dati del turno la nota dell'archivio è
  `ARCHIVIO_NOTA_RICERCHE` (prima le ricerche di prima, poi «non lo so»), e con un'estensione
  nominata la riga delle ricerche le cede il posto (`RICERCA_EST`): le prime due coppie della
  tabella sono risolte, le altre restano.
- (c) Un tetto ai dati del turno, con l'ordine di (a), e la lunghezza nel registro (campo
  numerico, niente testo).

### 3.11 Cinque definizioni di «altra persona» — P2 (voce e conversazione in corso)

**Cosa.**

| Dove | Criterio | Effetto |
|---|---|---|
| Brain (`_check_conversation`) | proprietario ≠ chi parla | **chiude** la conversazione |
| Corsie | un'altra persona | apre un'altra conversazione e lascia stare la prima |
| Schermi (`schermi/conversazione.py` 137–160) | un ospite o una voce non riconosciuta | **chiude** la conversazione scritta |
| Compagnia | impronte acustiche, 300 s | nessun legame con l'identità |
| Sfida | `_speaker_key != persona` | `SFIDA_ALTRA_VOCE` |

**Dal registro.** Dal 06/10 `conversazione_altra_persona` scatta solo nella conversazione
anonima `ospite:<satellite>`. Esempio: il 09/10 alle 18:48 una frase giudicata
`minore_piu_protetto` finisce nella conversazione anonima e la svuota. La conversazione di chi
amministra riprende al turno dopo (`come: ripresa`), ma il minore non ha una conversazione sua.

**Altre conseguenze.**
- `sospeso_altra_persona` (`brain.py` 2417) viene dopo `_check_conversation`, che ha già chiuso:
  è quasi irraggiungibile (1 volta in 8 giorni).
- Chi amministra con un minore vicino riceve tre esiti per la stessa frase:
  - per le corsie è «voce», quindi la sua conversazione;
  - per gli schermi è «conversazione», quindi non la rinnova;
  - per il livello è familiare.
- Il doppione fra satelliti si scarta dopo l'identità: la stessa frase aggiorna l'impronta due
  volte (`registry.adapt`) ed entra due volte nella memoria della compagnia.

**Proposta.**
- Un solo criterio, quello delle corsie (una conversazione per persona, mai chiusa da un'altra);
  Brain e schermi lo seguono.
- `minore_piu_protetto` porta alla conversazione del minore.
- Il doppione si controlla prima di `_chi_parla`.

Da passare al ramo `sera-voce-conversazione`, se non lo copre già.

### 3.12 Tempi diversi per lo stesso concetto — P3

| Concetto | Valore |
|---|---|
| Conversazione | 300 s |
| Proposta | 120 s e 3 turni |
| Sfida | 60 s, legata al **satellite** |
| Intento | **600 s**, ma vive nella conversazione |
| Continuità della voce | 900 s |
| Compagnia | 300 s |
| Riferimento della casa | 300 s |
| Riferimento dell'agenda | 600 s |
| Sviluppo sospeso | 30 min |
| Conferma di un'estensione | 120 s, chiave a parte |

**Conflitti.**
- L'intento oltre 300 s di silenzio non arriva mai, perché `conversazione_scaduta` lo cancella
  prima.
- La proposta segue la persona da un satellite all'altro; la sfida resta sul satellite.
- Un «grazie» (`record_courtesy`) non tiene viva la conversazione.
- Gli schermi contano dall'ultima frase riconosciuta dalla voce, Brain dall'ultimo turno.

**Proposta.** Documentarli in un solo posto (sezione di `voce-e-regole`) e vincolarli in
`Config`: `intento_valido_s ≤ storia_inattiva_s`, oppure l'intento fuori dalla conversazione.
Decidere se la sfida segue la persona.

### 3.13 Sviluppo e proposta in sospeso — P2

**Cosa.** `SVILUPPO_MSG` chiede al modello di chiudere con una frase sullo sviluppo; in più
`sviluppo_riga_fuori_tema` aggiunge da codice una riga in coda. La proposta però diventa
`pending` solo se la risposta **finisce con «?»** (`brain.py` 2127). Se il modello dice la domanda
di un tool e poi la frase dello sviluppo, la proposta si perde. Nel registro
`azione_in_sospeso` e `sviluppo_modalita` stanno insieme in 52 turni: succede spesso che ci sia
una domanda in modalità sviluppo.

**Proposta.**
- `pending` dalla proposta strutturata del tool (`_offer`, `in_sospeso`), non dalla
  punteggiatura finale.
- Togliere dal prompt la richiesta della frase finale: la riga di riserva da codice basta.

### 3.14 Due domande nella stessa risposta — P2 (in corso per la stessa chiamata)

**Cosa.** Non c'è deduplica delle chiamate. Il ramo `sera-politica-strumenti` aggiunge
`chiamata_ripetuta` per stesso tool e stessi argomenti. Restano due casi:
- due tool diversi che restituiscono ciascuno una domanda: si dicono tutte e due, ma `_offer`
  tiene solo l'ultima, quindi il «sì» vale per la seconda;
- `argomento_forse` («forse intendevi…?») sovrascritto da una domanda della politica nella stessa
  risposta.

**Proposta.** Al più una domanda alla persona per risposta: la prima chiude la risposta, e
l'altra chiamata riceve «c'è già una domanda in sospeso».

### 3.15 Il guardiano dei minori dopo i tool — P2 (da verificare sulla DGX)

**Cosa.** In `guardia.filtra` (`guardiano.py` 758–775) la domanda di un minore si giudica prima
della risposta solo se il guardiano usa lo stesso modello della voce (`condivide_voce`).
Altrimenti il generatore di `stream_reply` parte subito, e con lui la politica e i tool.

**Esempio costruito.** Il minore chiede un'azione della casa insieme a una frase di pericolo: con
un guardiano su un altro modello, l'azione può essere già eseguita quando arriva «pericolo».

**Proposta.** Con un minore che parla, `prima_del_tool` aspetta il giudizio della domanda, come
fa già per la «rivolta». Verificare sulla DGX quale modello usa il guardiano. Se condivide quello
della voce, oggi il caso non si presenta.

### 3.16 Regole e parametri senza effetto — P3

- `minori_margine_ambiguo` (0,05) non scatta mai finché `speaker_id_margine` (0,08) è più
  grande. Per «voce» la frase ha già 0,08 di margine sul secondo profilo.
- `conferma_breve` alza il livello ad amministra e subito dopo `compagnia_voce_nella_frase` lo
  abbassa a ospite: tutte e due le regole nello stesso turno, con esiti opposti.
- `voce_margine` e `minore_piu_protetto` scattano insieme per la stessa frase.
- `_NUMERI` è definito due volte in `politica.py` (lista a 960, dizionario a 1359). Il secondo
  sostituisce il primo, e `_numero_detto` funziona per caso.
- Negazione: `giustificata` e `politica_cambio_non_chiesto` cercano i verbi senza `_NEGATO`,
  mentre `ancorata` e `chiesto_con_verbi` lo usano. «Non aggiungere il latte» ancora la vecchia,
  non la nuova.
- Il flag `rifiutata_valore` si scrive sul turno vero anche quando poi lo sviluppo esegue: la
  chiamata dopo, nella stessa risposta, riceve subito la domanda.

## 4. Principio 10

Il criterio (`docs/ricerche/2026-10-01-regole-deterministiche.md`): una regola sul testo
riconosce una forma chiusa **per intero**, ha i contrari nelle prove e un nome nel registro.

**Riconoscono una parola dentro la frase** (non per forza un errore: il principio lo ammette per
i vincoli di sicurezza su una scelta già fatta, ma qui l'effetto non è sempre una domanda in più):

| Regola | Cosa fa con una parola dentro la frase |
|---|---|
| `politica._NO` | annulla il consenso con «non», «niente», «mai» ovunque (§ 3.5) |
| `politica._SI` | «si», «sicuro», «giusto» e «conferma» fra le prime 4 parole di qualunque pezzo |
| `valore.ANNULLA` | «no» in testa seguito da **qualunque** cosa chiude l'intento; `rifiuto` ha le eccezioni, lui no |
| `ciclo.py` 1804 e 1893 | prefissi «annulla/basta/stop», «no/non/nessuno»: «Non so… mi chiamo Marco» è un rifiuto del nome; **senza nome nel registro** |
| `brain.TOOL_REQUEST` | «cerca … foto» ovunque trattiene il testo |
| `ASKS_ABOUT_TOOLS` | «il comando» ovunque spegne `ToolNameHold` |
| `PARLA_ESTENSIONI` | «l'estensione del contratto» aggiunge l'elenco delle estensioni |
| `SVILUPPO_RIPRENDI` | «continua a piovere?» aggiunge gli sviluppi sospesi |
| `riferire._DELICATO` | contiene `calliope`: col nome in testa la frase è «delicata», e il controllo `uscita_istruzione` cambia |
| `riferire._COME_SI_FA` | «come» ovunque |
| `riferire._CHIEDE_CONTATTO` | «chiam…», «scriv…», «dove» ovunque |
| `riferire._bersaglio` | sottostringa: «Ada» in «adagio», «3» in «13» |
| `sicurezza.ACTION_REQUEST`, `_INTERNE` | dentro la frase di proposito, documentato: decidono solo se chiedere |

**Senza nome nel registro.**
- La cortesia soppressa da `has_pending` o da `ultima_domanda` (forma «conferma»).
- La proposta scaduta.
- La sfida con esito «no».
- Il «no» a una domanda aperta.
- `consenso` in `sonde.py` 201, che concede host di rete: va registrato.
- Le due regex di `ciclo.py`.
- Il taglio dei turni (`_trim_history`) e la compressione morbida (solo nel campo
  `compressione`).

**Senza il nome nelle prove.** 78 nomi non compaiono come stringa in `prove/` (qualcuno è
composto al volo, quindi il conto è per eccesso). Tra quelli che scattano davvero:
- `stop_interruzione`;
- `estensioni_elenco_turno`;
- `sviluppo_fase`, `sviluppo_analisi`, `sviluppo_revisione`;
- `schermo_zona_grigia`;
- `tool_argomenti_non_validi`;
- `immagine_in_ingresso`.

Da aggiungere, insieme ai contrari della tabella del § 3.5.

## 5. Cosa fare

**Subito (P1, piccoli e senza toccare ciò che fanno i tre rami della sera):**

1. Ombra con la decisione finale e attrito su quella (§ 3.4): la misura della fase 4 oggi
   conta male.
2. `tail` azzerato e ripiego sul vuoto nella passata finale (§ 3.7).
3. `installa_avvia`: la sfida resta, come pavimento per `cl.sfida` in `decidi_valore`;
   `politica_valore_detto` fra le regole che passano; `da_config` fidato (§ 3.8).
4. Motivo della sfida e fonte del valore veri (§ 3.3).

**Appena uniti i rami della sera (P1):**

5. Una funzione sola per «questo sì basta?» (§ 3.1), costruita sul `consenso_della_persona` del
   ramo della politica, con il consenso alle domande della nuova giudicato dalla nuova anche per
   E3 (§ 3.2).
6. Un modulo solo per sì, no, correzione e cortesia (§ 3.5), con le frasi della tabella come
   contrari; poi le uscite e lo stop che rispettano la proposta (§ 3.6).

**Dopo (P2):**

7. Precedenze e tetto dei dati del turno (§ 3.10), insieme al lavoro sulla ricerca.
8. `pending` dalla proposta strutturata e una domanda per risposta (§ 3.13, § 3.14).
9. Un criterio solo per «altra persona» e il doppione prima dell'identità (§ 3.11).
10. Nomi delle regole con l'esito (§ 3.9).
11. Il guardiano prima dei tool per i minori, da verificare sulla DGX (§ 3.15).
12. Dopo una settimana di fase 4, ridurre la politica di prima a ciò che passa (§ 3.8).

**Da documentare (P3):** tempi (§ 3.12), parametri senza effetto e regole doppie (§ 3.16),
regole del principio 10 senza nome o senza contrari (§ 4).

**Una regola di metodo, per non ricadere qui.** Prima di aggiungere una regola sul consenso,
sull'identità o sulla conversazione, cercare se lo stesso ingresso è già giudicato altrove
(tabelle dei § 1.3 e § 3.1) e, in quel caso, cambiare quella invece di aggiungerne una accanto.
Anche le correzioni buone di questi giorni, una per una, hanno spesso aggiunto un criterio
accanto a quelli che c'erano (§ 3.1, § 3.5).
