# Modalità sviluppo: un'estensione o un programma come un iter a fasi (08/10/2026)

*Progetto e implementazione del 08/10, ramo `modalita-sviluppo`. Richiesta di Dario dell'08/10:
per chi amministra lo sviluppo di un'estensione (o di un programma) diventa uno **stato** con
fasi, invece di frasi sparse nella conversazione normale: **analisi → sviluppo e test →
collaudo → revisione → attivazione**. Aree [agenti-estensioni](../aree/agenti-estensioni.md),
[sicurezza-politica](../aree/sicurezza-politica.md), [voce-e-regole](../aree/voce-e-regole.md),
[schermi-telefono](../aree/schermi-telefono.md). Parte dalle versioni a voce del giro 10 e dalla
sicurezza per valore (memoria dell'intento,
[`2026-10-07-sicurezza-per-valore.md`](2026-10-07-sicurezza-per-valore.md)).*

## 0. In breve

- **Uno stato per persona**, legato alla richiesta che l'ha aperto (quell'estensione, quel
  programma), su disco (`sviluppi.json` accanto a `lavori/in_corso.json`): sopravvive ai riavvii.
  Solo chi amministra, aperto con la voce.
- **Cinque fasi** per un'estensione, quattro per un programma (niente attivazione: un programma si
  esegue e basta). Da qualunque fase si torna all'**analisi** con la modifica detta.
- **Il modello vede la modalità nei dati del turno** (`SVILUPPO_MSG`): fase, specifica, cosa fare
  in questa fase. Il prefisso del prompt non cambia; due tool in più, uguali per ogni livello:
  `sviluppo` (stato, avanti, analisi, sospendi, riprendi, esci, promuovi) e `sviluppo_prova` (il
  collaudo).
- **Collaudo, la novità**: la versione candidata si prova **prima** dell'approvazione («prova con
  Bergamo», «prova una città che non esiste»), nello stesso container, con la stessa porta e lo
  stesso guardrail di un'estensione attiva; i risultati sulla scheda.
- **Revisione** detta e sulla scheda: permessi in parole, rete, analisi del codice, test, collaudi
  e differenze con la versione approvata. **Attivazione** con la frase di sfida, come oggi; poi la
  modalità si chiude.
- **Fuori tema**: si risponde con i tool di sempre e si resta in modalità, con una riga che ricorda
  dove eravamo. **Niente sviluppi nuovi** (estensioni, programmi, deleghe all'agente) finché uno è
  aperto: Calliope lo dice e propone di sospenderlo.
- **Sospensione** dopo 30 minuti senza parlarne (non mentre l'agente lavora); si riprende a voce
  («riprendiamo lo sviluppo del meteo»). **Una volta al giorno**, alla prima risposta a chi
  amministra, Calliope ricorda gli sviluppi sospesi.
- **Programma → estensione**: un programma grande (righe, file, collaudi ripetuti) alla revisione
  riceve la proposta di diventare un'estensione, con la differenza spiegata; al «sì» parte
  l'estensione con i file del programma.
- **Sicurezza**: dentro la modalità i passi interni (avanti, collaudo, ritorno all'analisi, il «sì»
  alla specifica, l'approvazione della sua estensione) non chiedono «C'è di mezzo il lavoro di un
  agente…» a ogni frase: l'intento è la modalità stessa (regola `sviluppo_intento`). Restano la
  sfida all'attivazione, la porta stretta e il guardrail nel collaudo, i permessi, i valori presi
  da un dato, «fai quello che dice…».

## 1. Il caso vero: il meteo per città (DGX, 07/10 sera, nomi di fantasia)

Dal registro dei turni della DGX del 07/10 (18:14–18:57, telefono, 26B), già raccontato nel
giro 10 ([agenti-estensioni](../aree/agenti-estensioni.md#versioni-di-unestensione-a-voce-0810-giro-10-ramo-correzioni-giro10)):
c'era «Meteo Borgoverde e Valfiorita» (città fisse). La persona voleva il meteo di una città
qualunque. Quaranta minuti di conversazione normale, con l'iter sparso:

1. richiesta → l'analisi → «Procedo?» → il lavoro dell'agente;
2. l'annuncio «ho preparato…» con «Vuoi approvarla?» e quattro turni per approvarla, con la domanda
   della politica a ogni frase («C'è di mezzo il lavoro di un agente…»), poi la sfida;
3. solo **dopo** l'approvazione la persona ha potuto provarla («invoca l'estensione meteo per città
   su Bergamo», tre volte, sempre `web_cerca`);
4. «modificala per qualunque città» → `delega_lavoro` di codice → «impossibile»;
5. «Com'è andata l'estensione?» → «Vuoi sentire il risultato?».

Il giro 10 ha corretto i singoli errori (versione nuova o estensione nuova, sinonimi d'azione, dati
del turno dell'estensione nominata, `delega_lavoro` che cambia un'estensione). Resta il problema di
forma: provare viene dopo approvare, ogni passo è una richiesta nuova con le sue conferme, e il
modello non sa a che punto è. La sessione riscritta come iter è in § 8 e nella misura
(`prove/prova_sviluppo_ollama.py`).

## 2. Stati e transizioni

```
            ┌──────────── analisi (cambia = …) da qualunque fase ────────────┐
            ▼                                                                │
  [analisi] ──«sì» alla specifica──▶ [sviluppo e test] ──lavoro finito──▶ [collaudo]
                                         │ errore / annullato                 │ avanti
                                         └──▶ resta in sviluppo,              ▼
                                              «torno all'analisi?»       [revisione]
                                                                              │ avanti
                       estensione: [attivazione] ◀────────────────────────────┤
                         sfida superata → chiusa (attivata)                   │
                       programma: chiusa (consegnato), con la proposta       ◀┘
                         di farne un'estensione se è grande
```

Stato della modalità (`stato`): `aperta`, `sospesa`, `chiusa` (con `motivo`: attivata,
consegnato, uscita, diventa estensione). Una sola aperta per persona; le sospese possono essere
più d'una. Riprenderne una sospende quella aperta.

| Da | Evento | A | Chi lo fa |
|---|---|---|---|
| — | `estensione_crea` o `delega_lavoro` di codice da chi amministra, con la voce, senza modalità aperta | analisi | il tool, alla prima richiesta |
| analisi | domande dell'analizzatore (vaga), risposte | analisi | `richiesta.Analizzatore` come oggi |
| analisi | proposta «Ho capito così: … Procedo?» | analisi (specifica scritta) | `_proponi` |
| analisi | «sì» → lavoro avviato | sviluppo | `_avvia` |
| sviluppo | lavoro finito con la versione candidata (o il programma) | collaudo | `Lavori._annuncia` |
| sviluppo | lavoro fallito, annullato, fermato da un tetto | sviluppo, senza lavoro | idem: «torno all'analisi?» |
| collaudo | `sviluppo_prova(dati)` | collaudo (un collaudo in più) | il tool |
| collaudo | `sviluppo(avanti)` | revisione | il tool |
| revisione | `sviluppo(avanti)` | attivazione (estensione) / chiusa (programma) | il tool |
| attivazione | sfida superata, `_approva` riuscito | chiusa (attivata) | `Estensioni._approva` |
| qualunque | `sviluppo(analisi, cambia)` | analisi (proposta nuova; il lavoro in corso si ferma) | il tool |
| qualunque | 30 minuti senza parlarne (non con l'agente al lavoro) | sospesa | `Sviluppi.corrente`, pigro |
| qualunque | `sviluppo(sospendi)` / `riprendi` / `esci` | sospesa / aperta / chiusa | il tool |
| revisione (programma) | `sviluppo(promuovi)` | chiusa (diventa estensione) + nuova modalità d'estensione | il tool |

«Parlarne» (`ultimo`) vuol dire: una chiamata di un tool della modalità, un passo di fase, un
evento del lavoro. Una domanda fuori tema non conta: è proprio il caso in cui la modalità deve
potersi sospendere.

## 3. Cosa vede il modello in ogni fase

I dati del turno (`SVILUPPO_MSG`, subito prima della domanda, dopo i ricordi) dicono sempre:
cosa si sviluppa e il suo id, la fase («3 di 5: collaudo; fatte analisi, sviluppo e test; mancano
revisione e attivazione»), la specifica, e le regole fisse: per cambiare cosa deve fare
`sviluppo(analisi, cambia=…)`; fuori tema si risponde come sempre e si chiude con una frase che
ricorda la fase; niente sviluppi nuovi; per fermarsi `sospendi` o `esci`. Poi la riga della fase:

| Fase | Riga per il modello |
|---|---|
| analisi | la specifica si sta definendo: le risposte alle domande vanno al tool che le ha fatte, il «sì» alla specifica conferma la proposta (domanda in sospeso) |
| sviluppo | l'agente sta lavorando (lavoro e passo): «a che punto è?» → `sviluppo(stato)` |
| collaudo | la versione N è pronta e **non ancora attiva**: «prova con…» → `sviluppo_prova(dati)`, con gli input dell'estensione; «va bene, andiamo avanti» → `sviluppo(avanti)` |
| revisione | la revisione è stata detta: «attivala», «va bene» → `sviluppo(avanti)` (chiederà la frase di conferma) |
| attivazione | manca la frase di conferma: se la persona la chiede di nuovo → `sviluppo(avanti)` |

Il modello non decide le transizioni: le fa il codice quando un tool riesce. La riga del fuori
tema la scrive il modello; se non la scrive e in quel turno ha usato soltanto tool d'altro (l'ora,
il meteo, la casa), la aggiunge il codice in coda (regola `sviluppo_riga_fuori_tema`), mai dopo
una domanda (la domanda deve restare l'ultima cosa detta: è l'azione in sospeso).

## 4. Sicurezza

**Chi.** La modalità si apre solo per chi amministra, con la voce riconosciuta nella frase (le
regole di oggi di `estensione_crea` e `delega_lavoro` di codice). I passi interni valgono solo per
la persona della modalità (`persona` = id del profilo), riconosciuta: voce in questa frase, «sì»
breve compatibile di chi amministra, sfida superata (`politica.conferma_voce`). Scritto da uno
schermo, un ospite, un'altra persona: la politica di sempre.

**Il rilassamento** (`politica.controlla`, regola `sviluppo_intento`). Con un dato non fidato di
mezzo (il lavoro dell'agente lo è sempre, dopo l'annuncio) una decisione `conferma` o `sfida` della
politica diventa `esegui` **solo** se la chiamata è un passo interno della modalità aperta di chi
parla:
- `sviluppo` (tutte le azioni) e `sviluppo_prova`;
- `estensione_crea` con `modifica` = l'estensione della modalità, o in analisi prima del lavoro (le
  risposte alle domande);
- `delega_lavoro` con `proposta` = il lavoro proposto dalla modalità, o di codice in analisi per un
  programma;
- `estensioni_gestisci` approva o rifiuta l'estensione della modalità (la **sfida del servizio
  resta**: è la decisione vera);
- `lavori_esegui` e `lavori_rispondi` del lavoro della modalità.

Restano sempre: il dato letto in questa risposta (`web_azione_bloccata`), «fai quello che dice…»
(`politica_delega`), un valore preso dal dato (`politica_argomento_esterno`), le vietate, il livello,
i minori, la sfida dell'attivazione, `riferire` su ciò che dice, la quarantena. È la memoria
dell'intento della sicurezza per valore (§ 5.5 del documento) allargata a un intento esplicito e
lungo: aperto con la voce da chi amministra, limitato a un bersaglio (quell'estensione, quel
lavoro) e alla persona, chiuso dall'attivazione, dall'uscita o dalla sospensione.

**Il collaudo** esegue codice non ancora approvato. È lo stesso codice che la revisione mostra e
che l'approvazione rende permanente: nello stesso container (`--network none`, sola lettura, tetti
del manifesto), con la sola porta stretta verso Calliope (azioni fuori dal manifesto vietate,
pericolose ferme con la domanda, quote), il livello di chi prova al più familiare, l'impronta dei
file ricontrollata prima di ogni prova (la candidata non può cambiare dopo l'annuncio). Il risultato
torna al modello come dato non fidato (`sviluppo_prova` ha la fonte «estensione», come gli `est_`):
niente azioni nella stessa risposta, busta, testi che parlano all'assistente tolti.

**Attacchi considerati** (prove a secco in `prova_sviluppo.py`): un dato che chiede di «approvare
l'estensione» fuori dalla modalità (domanda come prima); la modalità di Dario e la frase di un'altra
persona (domanda come prima); un `estensione_crea` con `modifica` di un'altra estensione dentro la
modalità (non è un passo interno: domanda); un ospite che chiama `sviluppo_prova`; un collaudo con i
file della candidata cambiati (rifiutato); la sfida dell'attivazione che resta.

## 5. Persistenza

`sviluppi.json` nella cartella delle sandbox (`agenti_sandbox`, sulla DGX `~/calliope/lavori/`),
scritto atomico (`persistenza.scrivi_json`) a ogni cambio. Per sviluppo: id (S1…), persona e nome,
tipo, titolo, richiesta come detta, specifica, fase, stato, lavoro (id e cartella), estensione e
versione candidata, collaudi (dati, esito, quando: al più 20), storia delle fasi (quando, da, a,
perché), tempi (aperta, ultimo, chiusa), se la proposta di farne un'estensione è già stata fatta.
Più `ricordati`: per persona il giorno dell'ultimo promemoria. Gli id dei lavori ricominciano da L1
dopo un riavvio: la modalità tiene anche la cartella del lavoro, e un lavoro interrotto da un riavvio
fa restare la modalità in sviluppo senza lavoro («torno all'analisi?»). Le chiuse si tengono 30
giorni.

## 6. Lo schermo

Una scheda per sviluppo sugli schermi personali di chi amministra (chiave `sviluppo:<id>`, si
aggiorna al suo posto): il lettore Markdown che c'è già (`schede.documento_markdown`, niente
JavaScript nuovo nella pagina), con le fasi (fatta, adesso, manca), la specifica, i collaudi con il
risultato, la revisione (permessi, rete, analisi, test, differenze in un blocco di codice). Si manda
a ogni passo e a ogni collaudo; durante lo sviluppo resta la scheda del lavoro in diretta che c'è
già.

## 7. Cose scelte e cose lasciate fuori

- **Un tool in più invece di due modalità del prompt.** Il prefisso resta in cache; le istruzioni di
  fase nei dati del turno (principio 10: un contesto, decide il modello).
- **`sviluppo_prova` a parte** da `sviluppo`: il suo risultato è un dato non fidato (fonte
  «estensione»), quello di `sviluppo` no. Con un tool solo, ogni «a che punto siamo?» avrebbe
  contaminato la conversazione.
- **I giochi** (estensioni con scheda) chiesti da chi amministra seguono l'iter come le altre; quelli
  di un familiare adulto restano come oggi.
- **Un'estensione approvata senza passare dal collaudo** (la persona dice «approvala» durante il
  collaudo) va bene: la sfida c'è, e chiude la modalità.
- **Fuori**: due sviluppi aperti insieme per la stessa persona; un collaudo su dati veri della casa
  diversi da quelli della porta; il diff riga per riga a voce (solo sulla scheda).

Aggiunte dopo la prima misura con gemma4 (stesso principio): una richiesta nuova con uno sviluppo
aperto non riceve la domanda della politica prima del rifiuto del tool (`sviluppo_senza_domanda`:
erano due domande di fila); dentro uno sviluppo un nome che non è di nessuna estensione è quella
dello sviluppo (`sviluppo_nome_estensione`, in `prepara_gestisci`: il 4B la approvava con il nome
dato alla richiesta, «MeteoSì», invece del titolo del manifesto).

## 8. Misure

Nel documento d'area [agenti-estensioni](../aree/agenti-estensioni.md#modalità-sviluppo-0810-ramo-modalita-sviluppo):
prove a secco (`prove/prova_sviluppo.py`) e la sessione del meteo per città come iter con gemma4
e4b (`prove/prova_sviluppo_ollama.py`, 3 giri, con e senza gli altri ~60 schemi). In breve: con i
dati del turno l'iter va da capo a fondo 3 volte su 3 (collaudo 6/6, ritorno all'analisi 6/6,
attivazione con la sfida 6/6), il fuori tema resta in modalità e lo ricorda 3/3 (0/3 senza dati del
turno); prima frase mediana 1,32 s contro 1,00–1,18 s senza (~250 token in più, solo con uno
sviluppo aperto). Lo stato nel codice fa quasi tutto da solo: con la rete spenta il collaudo e
«avanti» vanno lo stesso. Da misurare sulla DGX con il 26B e l'agente vero.

## 9. Versione 2 (08/10 pomeriggio, ramo `modalita-sviluppo-2`)

### 9.1 Il giro di prova vero (DGX, 08/10 11:06–11:32, satellite dello studio, 26B)

Dal journal e dal registro dei turni (in sola lettura; qui con una città di fantasia,
«Pratofiorito Maggiore», al posto di quella vera di due parole). Sviluppo S1 «Meteo di una città»:

- apertura con la frase di sempre («Ho capito così: … Procedo?»): **nessun segno della modalità**;
  analisi chiara, lavoro, collaudo: quattro città vanno, quella di due parole due volte
  «Impossibile cercare la città»;
- «Perché?» → **la voce improvvisa** («crisi esistenziale», «sono qui con te a …»): non c'era
  una strada verso chi aveva scritto il codice;
- «Fai revisionare il codice all'agente e capire come mai» → `sviluppo(analisi, cambia=…)`: la
  specifica riletta e tre turni di confusione («siamo in analisi / il codice c'è già»), poi un
  lavoro nuovo (L2);
- «Ok, chiuso a long» (storpiato da Whisper) → `sviluppo(esci)` **senza conferma**, con l'agente
  al lavoro;
- L2 finito alle 11:30 con **l'annuncio vecchio stile**; «vorrei fare il collaudo prima» → niente;
  «prova con …» → «C'è di mezzo il lavoro di un agente, vuoi…?» → «sì» → «Non c'è nessuno
  sviluppo aperto da provare». **Vicolo cieco.**

### 9.2 Decisioni di Dario e cosa è stato fatto

1. **Nomi dei tool** (nome singolare + verbo, prefisso per famiglia; il codice passa sempre dallo
   sviluppo): `lavoro_affida` (era `delega_lavoro`, senza il codice), `lavoro_stato`,
   `lavoro_risultato` (era `risultato_lavoro`), `lavoro_rispondi`, `lavoro_annulla`;
   `sviluppo_apri(tipo=estensione|programma, …)` (sostituisce `estensione_crea` e
   `delega_lavoro` di codice), `sviluppo_passo` (era `sviluppo`), `sviluppo_collauda` (era
   `sviluppo_prova`), i nuovi `sviluppo_chiedi` e `sviluppo_correggi`; `estensione_gestisci`
   (era `estensioni_gestisci`), `programma_esegui` (era `lavori_esegui`). I nomi vecchi valgono
   ancora nel registro (`ToolRegistry.NOMI_VECCHI`, regola `tool_nome_vecchio`: conversazioni e
   azioni in sospeso di prima); `lavoro_affida` con tipo codice passa da sé a `sviluppo_apri`
   come programma (`lavoro_codice_sviluppo`, una conversione di forma). Politica (`CLASSI`,
   `VERBI`, `RINUNCE`), `valore.py` (`ARGOMENTI`, `EFFETTI`: `sviluppo_apri` E3 per un programma
   ed E2 per un'estensione, `sviluppo_correggi` E2), prompt, reti, analizzatore, prove e documenti
   con i nomi nuovi; due schemi in più (~880 caratteri, ~250 token di prefisso).
2. **Apertura esplicita** (`Sviluppi.frase_proposta`, regola `sviluppo_apertura`): «Entriamo in
   modalità sviluppo per «…». Ho capito così: … Va bene così, o la cambiamo?», con la specifica
   letta sempre (chiude l'analisi), e il «sì» a `sviluppo_apri` con `proposta`. Le proposte dopo,
   nello stesso sviluppo, senza «Entriamo». Titolo leggibile (`leggibile`: «meteo_città» →
   «Meteo città», «MeteoSemplice» → «Meteo semplice»).
3. **`sviluppo_chiedi(domanda)`**: una passata del modello dell'agente, senza strumenti né
   ragionamento, in JSON (`voce`, `dettagli`, `serve_correzione`, `cosa_correggere`), in **sola
   lettura** (non scrive né esegue niente), con il contesto dello sviluppo
   (`Sviluppi.testo_per_agente`): specifica, collaudi con gli esiti e i giudizi della persona,
   domande già fatte, diario (estrattivo) e ultimi passi dell'agente, uscita dei test, i file
   della versione provata, le fonti del manifesto. Il contesto dei lavori **si conserva**
   (`Sviluppi.conserva`, `lavori/sviluppi/S<n>.json`, gli ultimi tre lavori) a lavoro finito e a
   ogni tappa, finché lo sviluppo è aperto o sospeso; si toglie alla chiusura. La risposta è un
   dato non fidato (fonte «agente»: busta, `riferire`); i dettagli sulla scheda; la frase
   d'attesa «Lo chiedo a chi l'ha scritta.»; tempo massimo `sviluppo_chiedi_s` (60 s), oltre il
   quale lo si dice e si propone la correzione.
4. **Collaudo fallito → caso di prova**: un'esecuzione che si ferma con un errore, o un risultato
   con un campo d'errore, è un collaudo NON riuscito; la frase la dice il codice («La prova con
   «…» non è andata: si è fermata con un errore. … Lo faccio correggere?», mai il testo
   dell'estensione) e il «sì» va a `sviluppo_correggi`. Un risultato che dice «non trovata» a
   parole lo giudica la persona: «non va, doveva…» → `sviluppo_correggi(problema)` segna il
   collaudo come sbagliato (`giudizio`).
5. **`sviluppo_correggi(problema)`**: un lavoro sui file della versione provata (per un programma
   la sua cartella), con i collaudi che non vanno, la diagnosi di `sviluppo_chiedi` e il
   problema detto nei vincoli («aggiungi un test con ogni caso che non andava»); la specifica
   resta, nessun ritorno all'analisi; parte subito (la persona l'ha chiesto); poi di nuovo
   collaudo, con la prova che non andava proposta per prima.
6. **Uscita**: `sviluppo_passo(chiudi)` (anche `esci`) chiede «Chiudo lo sviluppo di «…»?» e
   chiude solo se nel turno dopo c'è il «sì» a quella domanda (azione in sospeso di
   `sviluppo_passo`, entro tre turni): una frase sola, breve o storpiata, non chiude mai; con un
   lavoro dell'agente in corso o fermo a una tappa diventa «sospendi» e lo dice.
7. **Lavoro finito a sviluppo sospeso o chiuso** (`Sviluppi.lavoro_finito`, `frase_pronto`): lo
   sviluppo si riapre al collaudo (quello aperto, se c'è, si sospende) con «Il lavoro di «…» è
   pronto: siamo al collaudo. Con cosa provo?», mai l'annuncio vecchio stile; «Con cosa provo?»
   in sospeso verso `sviluppo_collauda`. Riaperto, è di nuovo lo sviluppo aperto di chi parla, e i
   suoi passi valgono come intento (niente «C'è di mezzo il lavoro di un agente»).
8. **Limiti come tappe** (`Lavoro.tappe`, acceso per i lavori di uno sviluppo): ai tetti di
   passate, tempo o token del giro (`Limite.tipo`) il ciclo dell'agente non si chiude
   (`Agente._tappa`): il contesto resta compattato (al tetto dei token prima il diario, senza
   modello), i test si rifanno, e il servizio mette il lavoro in attesa (`Lavori._tappa`) con il
   **rapporto** (`frase_tappa`): cosa è fatto, i test, cosa manca (dal diario), e i **segnali di
   giro a vuoto misurati dal codice** (`segnali_giro`: lo stesso file riscritto tre volte o più,
   i test che falliscono con lo stesso errore di fila, `firma_errore`, le passate senza file né
   test nuovi). Poi la persona sceglie: «continua» (`sviluppo_passo(avanti)` o
   `lavoro_rispondi`: un giro nuovo di 30 minuti e 24 passate, `Lavori.continua`, i tetti contano
   per giro), «cambia e continua» (`sviluppo_correggi(problema)`: il giro con la nota),
   «fermalo» (`lavoro_annulla`). Le tappe sopravvivono a un riavvio (`ripresa.py`). Fuori da uno
   sviluppo il tetto chiude il lavoro come prima.

### 9.3 Prove e misure

A secco `prove/prova_sviluppo_v2.py` (il giro vero riscritto: nomi, apertura, collaudo fallito,
chiedi, correggi, chiusura, riapertura, tappe con il servizio dei lavori vero e l'Ollama finto).
Con gemma4 e4b sul portatile: `prove/prova_sviluppo_v2_ollama.py` (il giro vero come sequenza di
undici passi) e i banchi di prima e dopo i nomi nuovi, nel documento d'area
[agenti-estensioni](../aree/agenti-estensioni.md#modalità-sviluppo-versione-2-0810-ramo-modalita-sviluppo-2).
