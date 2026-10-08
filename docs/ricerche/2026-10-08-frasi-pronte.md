# Frasi pronte: inventario, vincoli, opzioni e misure (08/10/2026)

*Analisi del 8 ottobre 2026 sera, ramo `analisi-frasi`, su richiesta di Dario: quando entrano in
gioco i tool deterministici Calliope dice frasi scritte nel codice, sempre uguali, e la
conversazione diventa monotona, mentre le risposte del modello hanno il tono della persona.
Nessuna modifica al codice di Calliope. Dati: registro dei turni della DGX (sola lettura, 02–08/10);
nel documento solo le frasi del codice e i conteggi, mai testi detti dalle persone. Misura: banco
su Ollama locale (`prove/misura_frasi_pronte.py`, non registrato come prova). Aree:
[personalita](../aree/personalita.md), [voce-e-regole](../aree/voce-e-regole.md),
[sicurezza-politica](../aree/sicurezza-politica.md).*

## In breve

- **Più di una risposta su quattro è una frase pronta**: 239 risposte su 838 (28,5 %) nella
  settimana della DGX, 152 delle quali dette per intero così come sono scritte nel codice.
- **La monotonia è misurabile, e sta tutta lì**: tra le ultime 20 risposte alla stessa persona
  nello stesso giorno, una frase pronta si ripete **20,5 volte ogni 100**, una risposta del
  modello **2,2 volte ogni 100** (in tutto 7,4 ogni 100 risposte).
- **Le più dette sono poche**: la cornice della politica «C'è di mezzo {fonte}, quindi chiedo a
  te: vuoi che {cosa}?» (30 volte), «Ci lavoro in secondo piano: ti avviso quando è pronto.
  Intanto puoi chiedermi altro.» (25), le proposte dei lavori «È un lavoro di programmazione: lo
  affido all'agente… Procedo?» (13), gli annunci di fine lavoro (28), la cortesia del tono
  ironico (17). Una ventina di frasi fa circa il 60 % delle frasi pronte dette.
- **Il tono non arriva alle frasi pronte**: 153 delle 239 sono state dette a una persona con un
  tono suo (regola `tono_persona`). Solo la cortesia e il cambio di tono hanno frasi per tono; le
  altre sono neutre e quasi tutte **col tu anche nel tono formale** (194 frasi candidate del
  codice usano forme del tu).
- **Il modello che riformula non serve, oggi**: sul banco (gemma4 e4b, 18 frasi tipiche × 5 toni)
  la riformulazione con i fatti bloccati restituisce la frase **identica 62 volte su 90**, e
  quando cambia sbaglia spesso il senso: motivo inventato in un rifiuto di permesso (4 toni su 5),
  «Procedo?» diventato «Procedi?» (3 volte), la domanda della politica persa, e 9 chiamate di tool
  scritte nel testo (che `TextCallGuard` eseguirebbe una seconda volta). I «fatti da dire» dati al
  modello: identici 74 volte su 90.
- **La «coda» del modello costa zero in latenza ma vale poco**: generata mentre la frase pronta
  suona (pronta in 0,33 s mediani, contro ~3 s di voce della frase), passa il controllo
  automatico 87 volte su 90, ma è generica e a sua volta ripetitiva: 72 su 90 cominciano con
  «Spero…» o «Che…», «Spero che la tua giornata sia serena» 6 volte, «Il silenzio avvolge…» nel
  computer di bordo. Da riprovare solo col 26B della DGX.
- **Raccomandazione**: subito il campo nel registro per misurare (fase 0); poi un catalogo delle
  frasi più dette con **varianti scritte a mano per tono e registro, a rotazione per persona, e
  una forma breve la seconda volta** (opzioni a + d, latenza zero, fase 1); la politica si
  alleggerisce chiedendo meno (progetto dell'attrito), non cambiando le parole; la coda del
  modello solo come esperimento col 26B dietro una rete (fase 3). Sicurezza, sfida, permessi,
  numeri, versioni e domande in sospeso restano parola per parola.

## 1. Inventario

### 1.1 Dove nascono

Il contratto dei risultati dei tool (`calliope/brain.py`, `_final_text`, `_result_text`) ha tre
campi che diventano voce:

| Campo | Cosa succede | Nel codice |
|---|---|---|
| `risposta_finale` | detta così com'è, il turno finisce senza un'altra passata del modello (`stream_reply`: «Tool con la frase finale già pronta») | 85 righe in 31 file |
| `conferma` | data al modello nella seconda passata; detta così com'è solo se il modello resta muto (`conferma_al_posto_del_vuoto`) o dopo la frase di sfida | 134 righe in 37 file |
| `da_dire` | come `conferma` (ora, calcoli) | 17 righe in 8 file |

Fuori dai tool:

- **politica** (`calliope/politica.py`): «C'è di mezzo {fonte}, quindi chiedo a te: vuoi che
  {cosa}?», «Non me l'hai chiesto: vuoi che {cosa}?», ««{valore}» viene {fonte}, non da te: vuoi
  davvero che {cosa}?», e il prefisso «C'è di mezzo {fonte}.» davanti a una `risposta_finale`;
- **conferme e sfida** (`calliope/conferme.py`): `SFIDA_MSG`, `SFIDA_COSA_MSG`, `SFIDA_PARZIALE`,
  `SFIDA_VOCE_INCERTA`, `SFIDA_ALTRA_VOCE`, `SFIDA_FALLITA`, `SFIDA_SCADUTA`, `SFIDA_CHI_PARLA`;
- **permessi** (`tools/registry.py`, `REFUSAL`; `tools/spec.py`, `SCRITTO_VOCE`; rifiuti dei
  singoli tool, minori, guardiano);
- **lavori e sviluppo** (`agenti/servizio.py`: `_proposta`, `proponi`, `stato`, `frase_finale`;
  `tools/sviluppo.py`, `sviluppo.py`): proposte, avvio, stato, fine, tappe, collaudi;
- **annunci asincroni** (`ciclo.py`, `_annuncia_*`): agenda, documenti, installazioni, lavori,
  estensioni, giochi;
- **estensioni** (`estensioni/servizio.py`): «Fatto: «{nome}» è attiva, versione {n}. Da adesso
  puoi chiedermela.», la scheda della revisione «Revisione {}. Permessi: {}…»;
- **cortesia** (`cortesia.py`): l'unica già **per tono e a rotazione** (6 toni × grazie/conferma,
  1–4 frasi ciascuno, rotazione per processo);
- **tono e modalità** (`tools/builtin.py`, `_TONO_DETTO`; `modalita.py`, `frase`): una frase per
  tono, già detta nel tono nuovo;
- **frasi d'attesa** (`ToolSpec.announce`, 10 tool): già scelte a caso (`random.choice`) tra 1–4;
- **ripieghi di Brain**: «Non ci sono riuscita: puoi ripetere la richiesta?», «Fatto.» dopo la
  sfida senza esito, `_frase_fallita`.

Conteggio con l'albero sintattico del codice (script nella cartella temporanea della sessione,
non nel repository): **~1.460 stringhe candidate a essere dette**, esclusi descrizioni dei tool,
messaggi per il modello, esercizi, catalogo delle installazioni, capacità e satelliti. È una stima
larga (comprende errori che il modello riformula e testi delle schede): le frasi che si sentono
davvero sono molte meno, e quelle che contano per la monotonia sono una ventina (§ 1.2). Fra le
candidate, 194 usano forme del tu e 51 cominciano con «Fatto».

### 1.2 Quali si dicono davvero (DGX, 02–08/10)

Registro dei turni `~/calliope/registro/turni-*.jsonl`: 1.093 turni, 838 con una risposta (762
di chi amministra: è soprattutto l'uso di prova di questa settimana, con molta modalità
sviluppo). Ogni risposta è confrontata con i modelli delle frasi del codice (i segnaposto
diventano «qualunque testo»); più gli esiti che sono frasi pronte per costruzione (annunci dei
lavori, cortesia, saluto, installazioni).

| | Risposte | Ripetute tra le ultime 20 (stessa persona, stesso giorno) | Prima frase mediana / p90 |
|---|---|---|---|
| frase pronta | 239 (28,5 %; 152 per intero) | **49 → 20,5 ogni 100** | 1,27 s / 2,36 s |
| modello | 599 | 13 → 2,2 ogni 100 | 1,22 s / 3,17 s |
| tutte | 838 | 62 → 7,4 ogni 100 | |

Il tempo della frase pronta comprende la prima passata del modello che sceglie il tool; il
risparmio è la seconda passata. Dove non c'è nessuna passata (frase dopo la sfida superata) la
prima frase esce in **0,21–0,25 s**.

Per area: agenti e lavori 64, tool di base 52, politica 43, annunci di fine lavoro 28, cortesia
17, estensioni 10, modalità 6, documenti, casa e installazioni 4 ciascuno.

Le più dette (modelli del codice; i valori tra «» e i numeri sono segnaposto):

| Volte | Frase del codice | Dove | Classe |
|---|---|---|---|
| 30 | C'è di mezzo {fonte}, quindi chiedo a te: vuoi che {cosa}? | `politica.py` | politica |
| 25 | Ci lavoro in secondo piano: ti avviso quando è pronto. Intanto puoi chiedermi altro. | `agenti/servizio.py` (`proponi`) | avvio |
| 13 | È un lavoro di programmazione / È una funzione nuova di Calliope / È una ricerca a più passi: lo affido all'agente {dove}. {stima} e ti avviso quando ha finito. Procedo? | `agenti/servizio.py` (`_proposta`) | proposta |
| 8 | {nome}, il lavoro di «…» è pronto: siamo al collaudo. La versione {n} non è ancora attiva: prima la proviamo. I test passano, {a} su {b}. Con cosa provo? | annuncio dei lavori, sviluppo | annuncio |
| 17 | Prego, lo metto in conto. / Dovere, ogni tanto. / Lo prendo come un complimento. | `cortesia.py` (tono ironico) | cortesia |
| 7 | Non me l'hai chiesto: vuoi che {cosa}? | `politica.py` | politica |
| 6 | Ho capito così: {specifica}. … | `agenti/servizio.py` | proposta |
| 5 | Stiamo sviluppando «{}»: {fase}. | `tools/sviluppo.py` | sviluppo |
| 4 | Ironia accesa. Cercherò di non esagerare, promesso. | `_TONO_DETTO` | tono |
| 4 | Per {cosa}, ripeti: … | `conferme.py` (`SFIDA_COSA_MSG`) | sfida |
| 3+3+2 | Non ho lavori in corso. / … Gli ultimi finiti: … Vuoi sentire il risultato? / Non ho lavori che aspettano una risposta. | `agenti/servizio.py` | lettura |
| 3 | Fatto: «{}» è attiva, versione {n}. Da adesso puoi chiedermela. | `estensioni/servizio.py` | esito |
| 3 | Modalità {} attiva: … / Modalità normale: torno a rispondere a «{}»… | `modalita.py` | esito |
| 3 | D'accordo: lo faccio correggere a chi l'ha scritto. Ci lavora in secondo piano; quando è pronto rifacciamo la prova con «{}». | `tools/sviluppo.py` | sviluppo |
| 3 | «{}» viene {fonte}, non da te: vuoi davvero che {cosa}? | `politica.py` | politica |
| 3 | Revisione {}. Permessi: {}. La può usare {}. Analisi del codice: {}. Test: {}. | `estensioni/servizio.py` | revisione |
| 2 | I lavori di programmazione li può affidare solo chi amministra: chiedi a chi amministra. | `tools/agenti.py` | permesso |
| 2 | Prima devo dirti cosa affido all'agente e avere il tuo sì: chiedimelo di nuovo. | `tools/agenti.py` | proposta |

Anche alcune risposte del modello si ripetono, ma dipendono dai dati (l'ora, i gradi di una
stanza, «Sono le {ora}.» 12 volte): sono letture con `da_dire` o `conferma` già dette dal modello,
e non sono il problema.

## 2. Vincoli: cosa non si tocca

1. **Sicurezza e permessi, parola per parola.** La frase di sfida (le parole da ripetere sono il
   controllo stesso), i rifiuti per permesso (`REFUSAL`, minori, «solo chi amministra»), i
   segreti, le frasi del guardiano. Il rifiuto è una frase pronta proprio per non lasciare al
   modello un «ho registrato…» (prova del 26/09, `registry.py`); il banco lo conferma: chiesto di
   riformulare il rifiuto sui lavori di programmazione, il modello inventa un motivo («non posso
   fornire previsioni meteo») in 4 toni su 5.
2. **Le conferme della politica hanno l'oggetto esatto e la domanda in fondo.** «vuoi che
   {cosa}?» è l'azione in sospeso del turno dopo (`in_sospeso.domanda`, `PENDING_MSG`); il `{cosa}`
   e il «{valore}» sono ciò su cui la persona dice sì. Può cambiare al più la cornice («C'è di
   mezzo…, quindi chiedo a te»), mai l'oggetto né l'ordine (domanda ultima). Sul banco il
   computer di bordo, riformulando, ha messo la domanda in mezzo e ha perso il «?».
3. **Numeri, nomi, versioni, permessi in revisione, stati delle fasi** (versione N, test a su b,
   permessi dell'estensione, «non è ancora attiva»): sono fatti su cui la persona decide.
   Restano scritti dal codice; nemmeno le varianti a mano li toccano (stessi segnaposto).
4. **Le domande che diventano azioni in sospeso** («Procedo?», «Lo apro?», «Con cosa provo?»)
   restano domande, e in fondo. «Procedo?» → «Procedi?» (banco, 3 volte) rovescia chi agisce.
5. **Regole e prove che leggono le frasi**: `ACTION_CLAIM` e le spinte guardano anche le parole
   di Calliope (per questo la cortesia evita «Fatto.»), la domanda finale fa l'azione in sospeso,
   `riferire.controlla_testo` controlla gli annunci dei lavori, «risultato già detto» toglie una
   frase pronta ripetuta nella stessa risposta (07/10). Le prove contano su testi esatti:
   «Procedo?» in 20 file (69 righe), «Fatto.» in 29 (89), «C'è di mezzo» in 13 (30), «Lo apro?»
   in 12 (33), «ripeti:» in 10 (17), «Ci lavoro in secondo piano» in 7 (9). Le varianti devono
   avere un modo deterministico per le prove (§ 5).
6. **Principio 10** ([regole deterministiche](2026-10-01-regole-deterministiche.md)): le varianti
   non sono regole sul testo della persona (scelgono la forma di ciò che dice Calliope), quindi
   non lo toccano; la «forma breve la seconda volta» decide sulla storia di Calliope, non sul
   significato di ciò che dice la persona. Ogni scelta va comunque scritta nel registro (§ 5).
7. **Latenza** (principio 6): oggi la frase pronta dopo la sfida esce in ~0,2 s, e dopo un tool
   risparmia la seconda passata. Un'opzione che rimette il modello **prima** della frase pronta
   costa quella passata (sul banco locale +0,34 s mediani, p90 +0,66 s alla prima frase).
8. **Streaming e voce** (principi 5 e 6): ciò che si aggiunge è una frase in più dopo, mai un
   pezzo che trattiene la prima; niente elenchi, numeri in cifre, frasi brevi.
9. **Minori**: il guardiano giudica ogni frase detta a un minore; una frase del modello in più è
   una frase in più da giudicare (latenza e rischio).

## 3. Opzioni

### (a) Varianti scritte nel codice, per tono e registro, a rotazione

Per ogni frase un piccolo insieme di varianti, per tono (i 6 di `config.TONI`) e col «lei» nel
formale; scelta senza ripetere le ultime 2 dette **alla stessa persona** (la rotazione di
`Cortesia` è per processo e per tono: con 3 frasi l'ironico ha detto «Prego, lo metto in conto.»
8 volte).

- Pro: latenza zero, nessun rischio sui fatti (stessi segnaposto), verificabile da una prova a
  secco, coerente con ciò che c'è già (cortesia, `_TONO_DETTO`, `announce`). Risolve il «tu» nel
  formale, che oggi è un piccolo difetto.
- Contro: lavoro di scrittura (12 frasi × 6 toni × 2–4 varianti ≈ 150–250 frasi); nel tempo si
  riconoscono anche le varianti; le prove con il testo esatto vanno adattate.
- Rischio: basso, se una prova controlla segnaposto, domanda finale, registro e parole vietate.

### (b) Pezzo fisso con i fatti + pezzo libero del modello

**(b1) Coda**: la frase pronta parte subito e intanto il modello scrive una frase breve col tono
(≤ 10–12 parole, senza numeri, nomi, domande, azioni). Si dice solo se passa il controllo e se è
pronta prima che finisca la frase pronta; altrimenti si scarta in silenzio.

- Pro: nessuna latenza in più sulla prima frase; il tono vero del modello e della persona.
- Contro (banco): generica e ripetitiva con e4b; fuori luogo dopo una domanda di sicurezza
  («Spero che l'agente possa aiutarti con tutto.») o dopo un rifiuto («Spero che la tua giornata
  sia serena.»); dopo una frase che finisce con una domanda non si può mettere (la domanda deve
  restare l'ultima cosa detta). Una passata del modello in più per turno (GPU sulla DGX insieme
  al guardiano, al rilevatore e agli embedding); una frase in più per il guardiano dei minori.
- Rischio: medio-basso con il controllo (si scarta), ma il controllo automatico non vede la
  qualità: 87/90 passano, una decina vale la pena di dirle.

**(b2) Riformulazione con i fatti bloccati** e controllo che ci siano tutti, con ripiego sulla
frase pronta.

- Pro: in teoria il tono pieno. È l'unico modo visto sul banco che mette davvero il «lei» nel
  formale («chiedo a lei: vuole che…», «Desidera che io la apra?»).
- Contro (banco): identica 62 volte su 90 (nessuna varietà); quando cambia, errori di senso che
  il controllo dei fatti **non vede** (motivo inventato nel rifiuto: i fatti richiesti ci sono
  tutti); «Procedi?»; chiamate di tool scritte; latenza +0,34 s mediani alla prima frase.
- Rischio: alto per tutto ciò che ha numeri, oggetti di una conferma, permessi.

### (c) Frase pronta come «fatti da dire» invece di `risposta_finale`

Il risultato porta i fatti e il modello risponde (come `conferma`, o come `SFIDA_ESITO_MSG` dopo
la sfida, 08/10).

- Pro: un solo meccanismo, già usato per le letture.
- Contro (banco): il modello ripete la frase identica 74 volte su 90, quindi niente varietà,
  con la seconda passata da pagare, 11 chiamate scritte e «Procedi?» 2 volte. `risposta_finale`
  esiste proprio dove la seconda passata faceva danni (documenti in generazione, rifiuti).
- Rischio: medio; guadagno vicino a zero con e4b.

### (d) Adattamento al contesto: la seconda volta più breve

Se la stessa frase (stesso id) è stata detta alla stessa persona nella conversazione corrente
(o negli ultimi N turni), la forma breve: «Ci lavoro, ti avviso.» invece di «Ci lavoro in secondo
piano: ti avviso quando è pronto. Intanto puoi chiedermi altro.»; «Anche qui c'è di mezzo
{fonte}: vuoi che {cosa}?»; «Come prima: lo affido all'agente. Procedo?».

- Pro: latenza zero (anzi meno voce da sintetizzare e ascoltare); è ciò che fa una persona;
  colpisce proprio la ripetizione misurata (stessa persona, stesso giorno).
- Contro: serve sapere cosa è stato detto (id della frase pronta nella conversazione; la
  conversazione per persona c'è già, `corsie.py`).
- Rischio: basso; la forma breve tiene gli stessi fatti e la stessa domanda.

### (e) Altro

- **(e1) Dire meno spesso, non in modo diverso.** La frase più ripetuta è la conferma della
  politica (30 + 7 + 3 volte): il 07/10 15,8 domande ogni 100 turni, 68 % falsi positivi. Il
  progetto della sicurezza per valore
  ([2026-10-07-sicurezza-per-valore.md](2026-10-07-sicurezza-per-valore.md)) è la leva più forte
  sulla monotonia di questa classe; cambiare le parole di una domanda di sicurezza ne toglie
  solo un poco.
- **(e2) Un suono al posto della frase** nelle forme chiuse dove la persona vede o sente l'esito
  (modalità startrek: «timer avviato» come segnale, come già il nome da solo col suono
  d'inizio ascolto). Solo per gli esiti senza fatti nuovi, e solo dove la modalità ha i suoni.
- **(e3) Forme essenziali** per i toni essenziale e computer di bordo: varianti più corte («In
  lavorazione. Notifica al termine.»), che sono già tono.
- **(e4) Unire le frasi di un turno**: «Ho capito così: …» + «È un lavoro di programmazione…» +
  «Procedo?» è lunga (proposta da 30–60 parole); la forma breve vale anche dentro una sola
  frase pronta composta.

### Quale opzione per quale classe

| Classe | Esempi | Opzione |
|---|---|---|
| Sfida, rifiuti per permesso, segreti, minori, guardiano | `SFIDA_*`, `REFUSAL`, «solo chi amministra» | **nessuna**: parola per parola |
| Conferme della politica | «C'è di mezzo…», «Non me l'hai chiesto…», «…viene da…» | **(e1)** chiedere meno; poi (a) solo sulla cornice e (d), con oggetto e domanda identici |
| Proposte e avvio dei lavori | «È un lavoro di programmazione… Procedo?», «Ci lavoro in secondo piano…» | **(a) + (d)**, «Procedo?» identica e ultima |
| Annunci asincroni | fine lavoro, collaudo, documenti, installazioni | **(a) + (d)** sulla cornice; numeri, versioni, test, «non è ancora attiva» fissi |
| Esiti di azioni senza domanda | timer, lista, estensione attiva, modalità, tono | **(a)** per tono e registro; (b1) solo come esperimento col 26B |
| Letture con frase pronta | «Non ho lavori in corso.», stato dello sviluppo | **(a) + (d)** |
| Letture già al modello | ora, gradi, calcoli (`da_dire`, `conferma`) | nulla: le dice già il modello |
| Revisione, permessi, versioni dello sviluppo | «Revisione… Permessi… Test…» | nessuna; (d) solo per non ripetere lo stato già detto |
| Cortesia | «Prego, lo metto in conto.» | **(a)** più varianti (6–8 per tono) e rotazione **per persona** |
| Ripieghi ed errori | «Non ci sono riuscita: puoi ripetere la richiesta?» | (a), 2–3 varianti |

## 4. Misura

Banco `prove/misura_frasi_pronte.py`: 18 frasi tipiche con valori di fantasia (le più dette del
§ 1.2 più letture, esiti, un rifiuto per permesso e una conferma della politica come controlli),
5 toni (normale, amichevole, ironico, formale, computer di bordo), 3 modi: **coda** (b1),
**riformula** (b2), **fatti** (c). 270 richieste a `gemma4:e4b-it-qat` sull'Ollama del portatile,
prompt di sistema vero (`Config.prompt_for` col tono della casa), prefisso già in cache, thinking
spento, temperatura 0,3. Controllo automatico: fatti presenti (alternative ammesse, per esempio
«10» o «dieci»), nessun numero o nome «…» nuovo, nessuna azione dichiarata nuova, domanda finale
conservata o non aggiunta, niente tu nel formale, niente «!» nel computer di bordo, nessuna
chiamata di tool scritta; per la coda niente numeri, nomi, domande, azioni, al massimo 14 parole.

| Modo | Passano il controllo | Identiche alla frase pronta | Prima frase (mediana / p90) | Fine (mediana) | Parole (mediana; frase 9,5) |
|---|---|---|---|---|---|
| coda | 87/90 (97 %) | — (79 code diverse su 90) | 0,31 / 0,40 s | 0,33 s | 7 |
| riformula | 76/90 (84 %) | 62/90 (69 %) | 0,34 / 0,66 s | 0,45 s | 10 |
| fatti | 77/90 (86 %) | 74/90 (82 %) | 0,33 / 0,65 s | 0,43 s | 11 |

Difetti trovati dal controllo: chiamate di tool scritte (riformula 9, fatti 11: `timer_imposta(10)`,
`promemoria_imposta(…)`, `lista_aggiungi(…)`), tu nel formale (2/2/3), domanda persa o aggiunta
(2), un fatto mancante (falso: «la informerò» per «ti avviso»).

Difetti che il controllo **non** trova, letti a mano:

- rifiuto per permesso riformulato con un motivo inventato («Non posso fornire previsioni meteo,
  devi chiedere a chi amministra»): 4 toni su 5, tutti «buoni» per il controllo;
- «Procedo?» → «Procedi?»: 3 volte (riformula 1, fatti 2);
- «Da adesso può chiedergliela» nel formale (sbagliato: «chiedergliela» è chiederla a lui), 2
  volte;
- «Il risultato è pronto.» ripetuto dal messaggio per il modello;
- coda: 72 su 90 cominciano con «Spero…» o «Che…»; «Spero che la tua giornata sia serena» 6 volte;
  «Il silenzio avvolge lo spazio circostante» e simili 12 volte nel computer di bordo; «tesoro»
  nell'amichevole; code affettuose dopo una domanda di sicurezza e dopo un rifiuto. A giudizio
  mio, una decina su 90 aggiunge qualcosa («Spero che l'idraulico sia di buon umore.», «Che
  meraviglia, un piccolo trionfo algoritmico.»).

Tono rispettato: nel formale la riformulazione passa al «lei» in 4 casi su 5 dove la frase aveva
il tu (l'unico guadagno vero); negli altri toni la riformulazione resta quasi sempre identica, e
il tono si vede solo nella coda.

Latenza. La coda parte in parallelo alla frase pronta: è pronta in 0,33 s mediani (0,42 s al
p90), mentre la frase pronta dura ~2–4 s di voce; quindi nessun ritardo sulla prima frase né buco
tra le due, sul portatile. La riformulazione e i fatti mettono il modello davanti: +0,34 s
mediani alla prima frase (p90 +0,66 s) sul portatile con e4b; sulla DGX col 26B da misurare.

Limiti: e4b sul portatile, non il 26B della voce sulla DGX (la DGX era in sola lettura e Ollama
lì serve Calliope); il banco non mette nella storia la chiamata del tool e il suo risultato,
quindi il modello crede l'azione ancora da fare: è la causa probabile di molte chiamate scritte,
che col flusso vero sarebbero meno ma non zero (con `TextCallGuard` una sola basta a rifare
l'azione); il giudizio sul tono è mio; il riconoscimento delle frasi pronte nel registro è per
modelli del codice, quindi approssimato (e il registro è di una settimana di prove, soprattutto
di chi amministra).

## 5. Raccomandazione a fasi

**Fase 0 — misurare (subito, piccola).**
- Nel registro dei turni un campo `pronte`: gli id delle frasi pronte dette nel turno (per
  esempio `lavori.avviato`, `politica.conferma`, `cortesia.grazie`) con la variante scelta e
  `breve: true` se è la forma breve. Gli id li scrive chi produce la frase (tool, politica,
  annunci), come `note_rule`.
- In `calliope stato --turni` una riga «ripetizioni ogni 100 risposte», separata per frasi
  pronte e modello: risposta normalizzata (numeri e «…» tolti) uguale a una delle ultime 20 della
  stessa persona nello stesso giorno. Riferimento di oggi: **20,5** (pronte), **2,2** (modello),
  **7,4** (tutte). Obiettivo dopo la fase 1: pronte sotto 8.

**Fase 1 — catalogo con varianti e forma breve (opzioni a + d; latenza zero).**
- Un modulo (per esempio `calliope/frasi.py`) con le frasi per id: segnaposto, varianti per tono
  (i 6 di `TONI`) e registro (lei nel formale), una forma breve. `frase(id, ctx, **valori)`
  sceglie col tono di chi parla o della casa (come `Cortesia.tono`), non ripete le ultime 2
  varianti dette a quella persona, e usa la forma breve se lo stesso id è stato detto nella sua
  conversazione negli ultimi N turni. Scrive l'id nel registro.
- Prima le frasi del § 1.2 (avvio e proposta dei lavori, annunci di fine lavoro, stato dei
  lavori, estensione attiva, modalità, correzione dello sviluppo, ripieghi) e la cortesia (più
  varianti, rotazione per persona): sono ~60 % delle frasi pronte dette.
- Fuori dal catalogo, o con una sola forma bloccata: sfida, permessi, segreti, minori, revisione.
- Per la politica, solo la cornice e la forma breve, dopo l'attrito (fase 2).
- Prove (livello 1, a secco, `prove/prova_frasi.py` da registrare nell'area personalità):
  - stessi segnaposto in tutte le varianti e nella forma breve di un id;
  - la domanda finale identica per gli id che creano un'azione in sospeso, e uguale a
    `in_sospeso.domanda`;
  - niente forme del tu nelle varianti del formale; niente «!» nel computer di bordo;
  - nessuna variante che dichiara un'azione (`ACTION_CLAIM`, «Fatto») se l'originale non lo fa;
  - rotazione senza ripetizioni, forma breve solo dopo la prima volta nella conversazione;
  - nessun id delle classi bloccate nel catalogo;
  - modo deterministico per le prove (variante 0 con un'impostazione delle prove, così le 30 e
    più prove che leggono i testi esatti non cambiano) e un caso che lo verifica.

**Fase 2 — chiedere meno (dopo il 10/10, già in programma).** L'attrito della politica per
valore ed effetto toglie la maggior parte delle «C'è di mezzo…, quindi chiedo a te». Dopo, la
forma breve per la seconda conferma nella stessa conversazione.

**Fase 3 — coda del modello, esperimento (dopo, sulla DGX).**
- Prima rifare il banco col 26B della DGX (`CALLIOPE_MISURA_URL`, `CALLIOPE_MISURA_MODELLO`) con
  la storia completa (chiamata e risultato del tool), in un momento in cui Calliope è ferma.
- Se la qualità sale (criterio: almeno 2 code su 3 da dire, giudicate a mano su 60), dietro una
  rete `coda_tono` della categoria «modello» (`config.RETI`), spenta per profilo: solo esiti e
  annunci che non finiscono con una domanda, solo toni amichevole e ironico, mai con un minore,
  mai dopo politica, sfida, rifiuti; generata in parallelo, scartata se arriva dopo la fine della
  frase pronta o se il controllo fallisce (regola `coda_tono` o `coda_tono_scartata` nel
  registro, campo `coda_ms`).
- La riformulazione (b2) e i fatti al modello (c) **no** con e4b; da rivalutare solo per il
  formale (tu → lei) col 26B, e comunque mai per le classi del § 2.

**Cosa scrivere nel registro dei turni, in sintesi**: `pronte` (id, variante, breve), le regole
`frase_breve`, `coda_tono`, `coda_tono_scartata`; in `calliope stato --turni` le ripetizioni ogni
100 risposte (pronte, modello, tutte) e la loro tendenza per giorno.

## 6. Script

- `prove/misura_frasi_pronte.py` — il banco del § 4 (misura, non registrata come prova).
- Cartella temporanea della sessione, non nel repository: l'inventario con l'albero sintattico
  (`inventario.py`), i modelli delle frasi per il registro e il conteggio sulla DGX (sola lettura,
  stampa solo aggregati).
