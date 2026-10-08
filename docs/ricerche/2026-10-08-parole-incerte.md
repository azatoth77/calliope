# Parole incerte: chiedere alla persona e imparare le correzioni (08/10/2026)

Idea di Dario dell'08/10 sera: quando Calliope non è sicura di una parola trascritta da Whisper,
(1) chiederlo alla persona, sullo schermo personale se c'è (un campo da correggere, come
«scrivere invece di parlare») o a voce («ho capito X, è giusto?»); (2) tenere un dizionario
delle correzioni confermate, da usare quando Whisper sbaglia di nuovo nello stesso modo.

Questa è un'analisi: nessuna modifica al codice di Calliope. Misure con
`prove/misura_parole_incerte.py` (manuale, non nel runner) e il nuovo insieme di frasi
`prove/riferimenti_nomi.tsv`; il registro dei turni della DGX letto in sola lettura, solo
conteggi e i casi tecnici dell'08/10. **Nomi di fantasia**: i due comuni veri del collaudo sono
qui «Pratofiorito Maggiore» (come nelle prove del giro 3) e «Pradello Dugnasco».

## I casi veri dell'08/10 (DGX, collaudo dell'estensione Meteocittà)

| ora | detto | trascritto | cosa è successo |
|---|---|---|---|
| 14:43 | Pratofiorito Maggiore | «Pratofiorino Maggiore» | il 26B ha scritto da sé il nome giusto nel collaudo; la provenienza lo vedeva «dal lavoro di un agente» (corretto nel giro 3 con `provenienza.vicina`) |
| 15:11, 18:50 | Mantova | «Mantua» | passato così all'estensione: alle 15:11 non trovato, alle 18:50 (versione nuova) il geocoder ha trovato Mantova |
| 15:28 | Pradello Dugnasco | «Pradello Duniasco» | il 26B ha scritto il nome giusto (non trovato lo stesso, per la codifica dell'URL dell'estensione) |
| 15:44 | Pradello Dugnasco | «Pradello Duniasco» | passato così: «non l'ho trovata»; Dario lo ripete da solo 18 s dopo e va |
| 17:11 | Lucca | «Luca» | l'estensione trova **Šipanska Luka** in Croazia: risultato sbagliato ma plausibile |
| 18:21 | Pradello Dugnasco | «Patello Giugnasco» | passato così, non trovato |
| 20:11 | Pradello Dugnasco | «Patello Duniasco?» | nessun tool; poi «Forse lo pronuncio male. Pradello Dugnasco.» → trovato |
| 15:36, 20:04 | Meteocittà | «metricità» | alle 15:36 il modello ha proposto un'estensione nuova accanto (difetto corretto nel giro 3); alle 20:04 ha ripreso proprio Meteocittà |
| tutto il giorno | l'agente | «la gente» | nel registro di 7 giorni «gente» in 13 turni, «agente» in 4; dal giro 5 il contesto dello sviluppo lo dice al modello |
| 20:13 | Sì, voglio attivarla | «Szi, vogliati várla!» | il modello ha capito «avanti» e la **sfida** ha chiesto la frase: nessun danno |

Tre lezioni prima ancora delle misure:

- **Il modello corregge già molto da sé** (14:43, 15:28, Meteocittà alle 20:04, «la gente» col contesto): i
  nomi noti e quelli di città grandi li sistema. Restano i nomi poco noti (un comune di due
  parole) e le parole vere al posto di altre parole vere («Luca», «la gente»).
- **L'errore costoso è quello che dà un risultato**: «Luca» → Šipanska Luka risponde con un
  meteo vero di un altro posto; «non trovato» invece fa ripetere la persona (20:11), cioè una
  domanda già c'è, solo implicita.
- **Le conferme e la sfida si difendono da sole**: «Szi, vogliati várla!» ha fatto il suo lavoro;
  una domanda sulle parole lì sarebbe solo attrito.

## 1. Cosa c'è già

- **`calliope/stt_correzione.py`** (05/10, spento): `confidenza` legge da `verbose_json` di
  whisper-server la probabilità per token e la riduce a parole (`parole_whisper`); `min_utile`
  esclude il nome che sveglia; `parole_incerte` le parole deboli rimaste nella frase;
  `Correttore` (variante C) manda la frase incerta al modello con il vocabolario della casa
  (`vocabolario_calliope`: persone, satelliti, schermi, stanze, entità e aree di HA, tool detti
  a parole) e `accettabile` tiene la correzione solo se cambia parole storpiate in parole che
  suonano simili. Nel registro `stt_confidenza` (parola più debole e quante sotto 0,5, mai le
  parole), solo quando il `verbose_json` è acceso.
- **Confronto A / B / B2 / C del 07/10** ([stt-tts](../aree/stt-tts.md)): B (le parole incerte
  nei dati del turno) **peggiora** — il modello commenta la trascrizione («non ho capito cosa
  intendi con un esogono») e chiede di più (27 domande di chiarimento contro 18 di A); B2 (frase
  capita trattenuta) è sicura ma col prompt vero quasi non agisce; C è l'unica che migliora la
  WER del banco (12,1 → 10,8 % vere, 20,6 → 17,9 % dominio) ma dal vivo scade al tetto di 1 s 13
  volte su 21 e fa correzioni «accettabili» pericolose («Usavamoci di Paola» → «Usa il numero di
  Paola», «teore suono» → «timer suono»). Si è restati su A. La **correzione cieca** è stata
  scartata perché cambia la frase senza che nessuno la veda, costa a ogni frase incerta e non
  sa distinguere «suona simile» da «è quello che ha detto».
- **`provenienza.vicina`** (giro 3, 08/10): una parola del valore che è una storpiatura di una
  parola detta vale come detta. È stretta di proposito (≥ 5 lettere, stessa iniziale, una
  lettera di differenza, due da 9 in su): è un vincolo di sicurezza, non un correttore.
- **Giro 5**: «chiedi alla gente…» con uno sviluppo aperto è una domanda all'agente — contesto
  del turno, non regola sul testo.
- **Moduli sullo schermo personale** (`calliope/schermi/moduli.py`, 03/10): un campo per dato,
  i valori vanno dritti al programma, solo agli schermi personali di chi ha chiesto, mai nella
  zona grigia, chi arriva prima (voce o modulo) vince. È lo stampo giusto per la scheda di
  correzione.
- **Trappole note**: il prompt di Whisper non si allunga (lo ricopia sull'audio incerto e
  inserisce il nome: falsi risvegli); whisper.cpp non ha hotwords.

## 2. La confidenza per parola

### Chi la dà, in che formato, quanto costa

- **whisper.cpp sulla DGX** (commit 60c0be6 del 02/10, `-bs 5 -l it`, letto in sola lettura):
  con `response_format=verbose_json` ogni segmento ha `words` con `probability` **per token**;
  `parole_whisper` le riunisce in parole (la minima dei token). La probabilità c'è anche con
  `token_timestamps=false` (campo per richiesta), identica fino all'ultima cifra.
  **Costo** (104 frasi vere, tre modi alternati, 08/10 sera, Calliope ferma da 18 minuti):
  `json` 0,222 s di mediana (p90 0,375), `verbose_json` 0,372 (0,447), `verbose_json` senza
  tempi per token 0,365 (0,493). Sono +0,15 s a ogni turno (il 07/10 nella prova end-to-end
  +0,10): non vengono dai tempi per token, e si pagano su tutte le frasi.
- **faster-whisper sul portatile**: `word_timestamps=True` dà `probability` per parola. Costo
  misurato sul portatile (GPU condivisa con altri processi): 0,315 → 0,355 s di mediana.
  Oggi `Transcriber` non lo chiede (`ultima_confidenza = None`).

### È affidabile sulle parole sbagliate?

Tre insiemi trascritti con tutte le probabilità: le **104 frasi vere** della taratura del 24/09,
le **150 di dominio** (sintetiche, tre voci di Piper con rumore rosa a 20 dB) e le **120 nuove
di nomi** (`riferimenti_nomi.tsv`, stesse tre voci: città di due parole di fantasia, città vere
come Lucca e Mantova, contatti, entità della casa, estensioni, file, conferme, «chiedi
all'agente», più 4 frasi libere). Una differenza di soli spazi («Prato Fiorito» per
«Pratofiorito») non conta come errore; il nome «Calliope» è escluso.

**whisper.cpp (DGX)**:

| insieme | WER | parole sbagliate | di cui con p ≥ 0,9 / ≥ 0,7 / ≥ 0,5 | a soglia 0,3: segnalate, di cui sbagliate, sbagliate trovate | a 0,5 |
|---|---|---|---|---|---|
| vere (104) | 13,7 % | 68 | 12 / 25 / 39 | 26, 54 %, 21 % | 54, 54 %, 43 % |
| dominio (150) | 19,5 % | 142 | 23 / 40 / 71 | 46, 91 %, 30 % | 99, 72 %, 50 % |
| nomi (120) | 30,6 % | 183 | 27 / 66 / 101 | 50, 74 %, 20 % | 116, 71 %, 45 % |

**Sui nomi negli argomenti** (108 frasi con un nome, sbagliato in 69):

| soglia | whisper.cpp: nomi sbagliati segnalati | nomi giusti segnalati | faster-whisper: sbagliati segnalati | giusti segnalati |
|---|---|---|---|---|
| 0,2 | 12/69 | 0/39 | 6/65 | 1/43 |
| 0,3 | 29/69 | 1/39 | 10/65 | 1/43 |
| 0,4 | 37/69 | 4/39 | 15/65 | 3/43 |
| 0,5 | 49/69 | 7/39 | 21/65 | 4/43 |
| 0,7 | 63/69 | 21/39 | 46/65 | 11/43 |

Cosa dicono:

- **Con whisper.cpp la probabilità è un buon segnale sui nomi, non sulle frasi**: a 0,5 segnala
  7 nomi sbagliati su 10 e solo 1 giusto su 6; sulle frasi vere invece una parola su due
  segnalate è giusta (rumore: articoli, attacchi detti in fretta). Quindi va guardata **solo
  sulle parole che finiscono in un argomento**, mai sulla frase intera.
- **faster-whisper è molto meno utile**: a 0,5 trova 21 nomi sbagliati su 65. Sul portatile
  (satellite e ripiego su CPU) non vale il costo.
- **Un errore su tre o quattro è invisibile**: whisper.cpp sbaglia 27 parole dei nomi con p ≥ 0,9.
  Sono le **parole vere al posto di parole vere**, gli stessi casi dell'08/10 riprodotti con le
  voci di Piper:

  | detto | trascritto (whisper.cpp) | probabilità |
  |---|---|---|
  | Chiedi all'agente… (6 frasi su 6, anche faster-whisper) | «alla gente» | 0,95–1,00 |
  | Prova con Lucca | «Luca» (2 voci su 3) | 0,84, 0,68 |
  | E adesso prova con Mantova | «Mantua» / «un manto» | 0,52 / 0,81 |
  | Attiva l'estensione Meteocittà | «metrocittà» / «nella velocità» | 0,45 / 0,82 |
  | Cercami il documento contratto affitto | «contatto affitto» | 0,88, 0,81 |
  | Cerca la sagra di Roccalba | «la saga di Roccalva» | 0,99, 0,23 |
  | Accendi la lampada del soppalco | «lampara del sottalco» | 0,84, 0,97 |

  Nessuna soglia li prende senza far domande su tutto. Per questi serve il **contesto** (lo
  sviluppo aperto per «la gente»), il **vocabolario** (Meteocittà è un'estensione) o l'**esito
  del tool** (Luca → un posto in Croazia).
- Le voci di Piper con nomi inventati sono più difficili della voce vera con nomi della casa
  (WER 30,6 % contro 13,7 %): i valori assoluti sono pessimisti, il confronto fra soglie e
  motori regge.

### Il vocabolario dei nomi noti

Per ogni nome sbagliato, il nome noto più simile (lettere senza spazi, doppie ridotte,
`difflib`), con un vocabolario di 55 nomi (quelli giusti delle frasi più satelliti, schermi,
persone e casa del banco di dominio):

| somiglianza | proposta giusta | proposta sbagliata | nessuna |
|---|---|---|---|
| ≥ 0,6 | 55/66 | 1 | 10 |
| ≥ 0,7 | 44/66 | 0 | 22 |
| ≥ 0,8 | 31/66 | 0 | 35 |

- Se il nome è **già noto** (un contatto, un'entità, un'estensione, una città già usata), il
  confronto a ≥ 0,7 lo ritrova due volte su tre e non ne sbaglia nessuno, **qualunque sia la
  probabilità di Whisper**: è il segnale più forte che abbiamo, e prende anche «metrocittà».
- **Solo sugli argomenti**: lo stesso confronto sulle frasi intere delle 104 vere dà un «forse
  intendevi» spurio in 16 frasi a 0,7 e in 5 a 0,8 («giorno» → Soggiorno, «storia» → Tobia).
- `provenienza.vicina` ritrova una parola del nome giusto in 20 casi su 66: va bene così per la
  sicurezza, non per suggerire.
- Limite: qui il vocabolario ha la risposta giusta dentro ed è piccolo. Con l'elenco dei comuni
  italiani (~7 900) le proposte sbagliate cresceranno: da misurare prima di usarlo per le città
  mai dette.

## 3. Quando chiedere

Regola di fondo: **solo per una parola che finisce in un argomento che nomina qualcosa** (la
città di un collaudo o del meteo, l'entità della casa, il contatto, l'estensione, il file, la
cosa da cercare), mai per la conversazione libera, mai per le parole di una conferma o della
sfida, mai per un ospite.

Dal registro dei turni della DGX (02–08/10, 992 turni con testo, conteggi):

- **172 turni (17,3 %)** hanno un tool con un argomento che nomina qualcosa: `sviluppo_collauda`
  45, `casa_stato` 21, `web_cerca` 19, `pc_apri_file` 18, `casa_comando` 16, `biblioteca_cerca`
  16, `sviluppo_prova` 8, `estensione_gestisci` 7, documenti, promemoria, liste. Nessuno da un
  ospite. L'08/10, giorno di collaudi, erano un terzo dei turni.
- **39 di questi (3,9 ogni 100 turni)** hanno il tool fallito (`ok: false`: non trovato, rete,
  politica…): `pc_apri_file` 11, `casa_comando` 10, `sviluppo_collauda` 7, `casa_stato` 6.
- **10 turni (1 ogni 100)** richiamano lo stesso tool entro tre turni con un argomento quasi
  uguale (somiglianza ≥ 0,75 su una parola): è la **correzione spontanea**, e prende i due casi
  dell'08/10 (Duniasco → Dugnasco, Luca → Lucca). Lo stesso confronto sulle parole delle frasi,
  senza il tool, scatta in 251 turni su 971 (estensione/estensioni, centro/cerro): inutile.

Domande in più ogni 100 turni, secondo quando si chiede (stime da queste misure):

| strategia | domande a voce ogni 100 turni | cosa prende |
|---|---|---|
| prima del tool, se una parola del valore è sotto 0,3 | ~2–5 | 4 nomi sbagliati su 10, quasi nessun giusto |
| prima del tool, sotto 0,5 | ~4–9 | 7 su 10, 1 giusto su 6 disturbato |
| **dopo un esito vuoto o un errore** del tool, se una parola del valore è debole o fuori dal vocabolario | **≤ 1–2** (tetto: 3,9) | i casi «non trovato» (15:44, 18:21, 20:11); non «Luca» |
| scheda sullo schermo personale, senza fermare il tool | 0 (una scheda, nessuna domanda) | tutto ciò che è segnalato, se la persona guarda |

L'attrito della politica è già 15,8 domande ogni 100 turni (07/10, 68 % falsi positivi): una
domanda in più **prima** di ogni tool con un nome incerto peggiora la cosa che Dario sta cercando
di togliere. Dopo un esito vuoto invece la domanda non costa un turno in più: il turno è già perso
e oggi la persona ripete da sola (20:11).

## 4. Come chiedere

**Sullo schermo personale (preferito, non blocca)**: il tool parte con ciò che ha capito
Whisper; sullo schermo personale di chi parla compare una scheda «Ho capito: Prova con
**Patello Giugnasco**» con la parola debole evidenziata, il campo precompilato e «Correggi» /
«Giusto» con un tocco. Come i moduli di oggi: solo schermi personali del proprietario
riconosciuto **dalla voce**, mai nella zona grigia né a uno schermo di stanza, mai per un
ospite; un valore inviato richiama lo stesso tool con lo stesso argomento corretto, e vale come
**scritto dalla persona** (canale `scritto`, provenienza della persona: non è un dato esterno);
nella storia entra «ho corretto … in …». Se intanto la persona ripete a voce, vince chi arriva
prima (`chiudi_per_tool`). Latenza della voce: zero.

**A voce, senza schermo**: solo dopo un esito vuoto o un errore, come ultima frase della
risposta, in una delle due forme:
- con un nome noto vicino (≥ 0,7): «Non trovo Patello Giugnasco: intendevi Pradello Dugnasco?»
  — un «sì» è una conferma breve, che oggi già funziona (`conferma_breve`);
- senza: «Non trovo Patello Giugnasco: me lo ripeti, o me lo scrivi sul telefono?». Lo spelling
  a voce non è misurato e Whisper sulle lettere sole è debole: «scrivimelo» è più sicuro.

Interazioni:
- **Half-duplex**: la domanda è l'ultima frase, e la finestra `followup_s` resta aperta per la
  risposta senza il nome.
- **Una domanda per turno**: con una conferma o una sfida in sospeso nessuna domanda sulle
  parole; la sfida già verifica ciò che conta (20:13).
- **Latenza**: la scheda non ne aggiunge; la domanda a voce dopo un esito vuoto non aggiunge
  turni rispetto a oggi; una domanda prima del tool costa un turno intero (~2 s di prima voce
  sulla DGX più la risposta).
- La confidenza deve arrivare fino al tool: oggi `t.conf_stt` resta nel ciclo. Serve sapere
  quali parole del valore vengono da quali parole della frase (lo stesso confronto di
  `tutto_detto`, con `vicina` per le storpiature).

## 5. Il dizionario delle correzioni

**Cosa contiene**: coppie «sentito → giusto» **per persona** e per contesto (tool e argomento:
`sviluppo_collauda.citta`, `casa_comando.entita`…), con data e numero di usi.

**Da dove si impara (solo correzioni confermate)**:
1. la scheda «Correggi» sullo schermo personale;
2. un «sì» a «intendevi X?» a voce;
3. la correzione spontanea: lo stesso tool richiamato entro tre turni con un valore quasi
   uguale, quando il primo è **fallito** e il secondo **riuscito**, dalla stessa voce
   riconosciuta (il caso delle 20:11). Senza esito (un tool che non dice se ha trovato) non si
   impara nulla.

Mai da un ospite, dalla zona grigia, da un testo scritto da un altro, da un dato non fidato
(risultato del web, lavoro di un agente, foto), né da un tool che il modello ha corretto da sé
senza che la persona lo dicesse.

**Come si usa**: **suggerimento, mai sostituzione nel testo** (principio 10: il significato lo
decide il modello; e «la gente» insegna che una sostituzione sul testo rompe le frasi in cui
«la gente» vuol dire la gente). Quando il valore di un argomento è un «sentito» del dizionario
(uguale, o `vicina`) per quella persona e quel tool, il risultato del tool o i dati del turno
dicono «di solito qui intendi «Pradello Dugnasco»». Insieme al dizionario conta il
**vocabolario dei nomi che Calliope conosce già** (estensioni, entità di HA con alias, rubrica,
persone, satelliti e schermi, città già usate con successo): lo stesso confronto, a ≥ 0,7,
solo sull'argomento.

**Cosa non serve e cosa non si fa**: il prompt di Whisper non si allunga con il dizionario
(trappola nota); whisper.cpp non ha hotwords; su faster-whisper `whisper_hotwords` esiste ma
vale per tutte le frasi e non è per persona: non lo si riempie.

**Rischi**:
- **Avvelenamento**: un ospite o una TV che «insegna» «Banca» → «Banca X»; per questo solo
  correzioni confermate dal proprietario riconosciuto, mai da canali non fidati, e il
  suggerimento non salta la politica: un valore che arriva dal dizionario è un valore che la
  persona ha già detto e confermato, quindi vale come **detto** per la provenienza solo per quella
  persona (da aggiungere a `provenienza`), e i tool pericolosi chiedono comunque la conferma.
- **Privacy**: il dizionario sta con la memoria della persona (memoria.db), mai nel registro dei
  turni (lì solo conteggi), si cancella con «dimentica le correzioni», non si legge ad altri.
- **Scadenza**: 90 giorni senza uso, al più qualche centinaio di coppie per persona.
- **Errori che si ripetono**: una coppia sbagliata confermata per errore continua a suggerire;
  per questo è solo un suggerimento e la scheda mostra sempre il testo di Whisper.

## 6. Raccomandazione a fasi

1. **F0, misura in ombra (nessun effetto)**: accendere il `verbose_json` sulla DGX per una
   settimana d'uso (+0,15 s a turno, misurati) oppure — meglio, a costo zero per la voce — tenere
   l'audio del turno e chiedere il `verbose_json` **solo** quando il modello chiama un tool con un
   argomento che nomina qualcosa, in parallelo al tool (≈ 0,37 s di GPU, nessuna attesa).
   Marcare nello schema dei tool gli argomenti che nominano (un campo della `ToolSpec`, per
   esempio `nomi=("citta",)`). Registro dei turni:
   - `stt_argomento`: `{tool, campo, min, sotto_04, noto, esito}` — probabilità minima delle parole
     del valore, quante sotto 0,4, se il valore è nel vocabolario, esito del tool
     (trovato/vuoto/errore); mai le parole;
   - regola di misura `correzione_argomento` (stesso tool, valore quasi uguale entro tre turni,
     con l'esito del primo e del secondo).
   Dopo una settimana: quanti esiti vuoti avevano un nome incerto o fuori vocabolario, e la soglia
   giusta sulla voce vera.
2. **F1, dopo l'esito vuoto**: un tool che cerca un nome e non trova nulla (o un'estensione che dà
   errore) aggiunge al risultato per il modello il nome noto più vicino («forse intendevi …») o
   l'invito a chiedere di ripeterlo o scriverlo. È contesto del turno, non una regola sul testo.
   Prove: a secco con i casi dell'08/10 in nomi di fantasia e i contrari (nome giusto e non
   trovato davvero: nessun «intendevi»; frase libera: niente), poi col modello su gemma4 e sul
   26B. Registro: `parola_chiesta {canale: voce, forma: intendevi|ripeti, esito}`.
3. **F2, la scheda sullo schermo personale**: dopo F1, per gli argomenti con una parola sotto 0,4
   (whisper.cpp) o fuori vocabolario, senza fermare il tool; con le regole di visibilità dei
   moduli. Registro: `parola_chiesta {canale: schermo, esito: giusta|corretta|ignorata, ms}`.
   Prova della pagina con node come per i moduli.
4. **F3, il dizionario**: solo quando F1 e F2 producono correzioni confermate da cui impararlo.
   Registro: `dizionario {suggerito, accettato}` (conteggi).

Da non fare: la correzione cieca (C) e le parole incerte al modello (B), già misurate; una
domanda a voce **prima** del tool; la confidenza sulla frase intera; il dizionario nel prompt di
Whisper; la confidenza di faster-whisper sul portatile (troppo debole sui nomi per il suo costo).

Misure ancora da fare: la soglia con la voce vera e nomi veri della casa (F0); il vocabolario con
l'elenco completo dei comuni; quante correzioni spontanee per settimana con l'uso normale (fuori
dai collaudi); la scheda con un telefono vero.

## Come rifare le misure

```
# frasi di nomi di fantasia (Piper, tre voci)
python prove/misura_parole_incerte.py sintetizza --uscita DIR_NOMI
# trascrizione con tutte le probabilità (DIR_STT: le 104 vere e le 150 di dominio, come misura_stt.py)
python prove/misura_parole_incerte.py trascrivi --dati DIR_STT --nomi DIR_NOMI --motore whispercpp --url http://127.0.0.1:8003/v1 --uscita wc.jsonl
python prove/misura_parole_incerte.py trascrivi --dati DIR_STT --nomi DIR_NOMI --motore faster --uscita fw.jsonl
python prove/misura_parole_incerte.py valuta wc.jsonl --elenco
python prove/misura_parole_incerte.py vocabolario wc.jsonl
```

Le richieste a whisper-server dell'08/10 sono passate da un tunnel `ssh -L` verso la porta del
server, con Calliope ferma da almeno 10 minuti: 374 frasi più 312 per il costo.
