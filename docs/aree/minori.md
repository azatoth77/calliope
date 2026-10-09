# Minori

*Fasce d'età, preset, guardiano, compiti, avvisi ai tutori. Documento d'area: nato il 06/10/2026 dividendo CLAUDE.md (proposta P7 di [`../ricerche/2026-10-06-analisi-complessiva.md`](../ricerche/2026-10-06-analisi-complessiva.md)). Chi lavora su quest'area aggiorna questo file; in CLAUDE.md al più una riga.*

## Moduli

| Stadio | Libreria | Dove |
|---|---|---|
| Minori (fasce d'età, preset per fascia, permessi nel codice, orari, compiti, avvisi ai tutori; dal 05/10) | SQLite (stesso file della memoria: `minori_regole`, `avvisi_tutori`, `compiti_giorno`); guardiano Llama Guard 3 8B su Ollama + rilevatore di pericolo (gemma4 e4b, output strutturato) | `calliope/minori.py` → `fascia`, `preset`, `permesso` (da `ToolRegistry.call`), `dato_turno`, `fuori_orario`, `piu_protetto`, `Compiti`, `Avvisi`, `estensione_consentita`, `conversazioni_visibili_ai_tutori`; `calliope/guardiano.py` → `Guardiano`, `filtra` (in `main.py`), `correggi_storia`; tool `compiti_aiuto`, `minore_gestisci` (`calliope/tools/minori.py`); terminale `python -m calliope.minori`; banchi `prove/prova_minori_ollama.py`, `prove/misura_guardiano.py`; [`docs/ricerche/2026-10-05-minori.md`](../ricerche/2026-10-05-minori.md) |
| Esercizi generati da Calliope (dal 08/10): matematica e italiano, a voce e sulla scheda, correzione nel codice, registro dei tentativi per i tutori | libreria standard; SQLite (stesso file della memoria: `esercizi_tentativi`, `esercizi_segnalazioni`, `esercizi_banco`); Wikizionario della biblioteca; secondo modello su Ollama | `calliope/esercizi/` → `matematica.genera`, `italiano.genera`, `numeri.leggi_valore`, `verifica.Wikizionario`, `verifica.SecondoParere`, `registro.Registro`, `sessione.Servizio`; tool `esercizi` (`calliope/tools/esercizi.py`); scheda `DISEGNA.esercizio` e `POST /api/esercizio`; rete `spinta_esercizi`; prove `prove/prova_esercizi.py`, `prove/prova_esercizi_pagina.py`, `prove/prova_esercizi_ollama.py`; [`docs/ricerche/2026-10-08-esercizi.md`](../ricerche/2026-10-08-esercizi.md) |

## Note dalla sezione «Stato attuale» di CLAUDE.md (fino al 06/10)

- **Minori** (05/10, `calliope/minori.py`, `calliope/guardiano.py`, rapporto
  [`docs/ricerche/2026-10-05-minori.md`](../ricerche/2026-10-05-minori.md)): profilo con data di
  nascita e tutori (speakers.json versione 2; «giovane» migra a «ragazzi»), aggiunto solo da chi
  amministra con voce e frase di sfida (`registra_utente` ora solo `amministra`; `arruola.py
  --nascita --tutore`); fasce piccoli < 7, bambini 7–10, ragazzi 11–13, adolescenti 14–17 con un
  preset ritoccabile per persona (`minore_gestisci`, `python -m calliope.minori`), come dato del
  turno al modello e nel codice per i permessi; voce incerta = profilo più protetto; guardiano
  (Llama Guard 3 8B, 0 falsi su 33 frasi giuste, 12/14 vietate fermate) su domanda e frasi solo
  per minori e ospiti, rilevatore di pericolo (gemma4 e4b, 9/10, nessun falso) con protezione,
  19696 e avviso ai tutori; compiti guidati, soluzione dopo 5 errori con avviso vero. Banco: 26B
  sulla DGX 48/48, 4B 45/48 (il 4B non conta i tentativi dei compiti); prima frase dei minori
  sulla DGX 1,36–1,48 s contro 0,89 senza guardiano, adulti invariati.

## Guardiano che non tace (06/10, Q3 della seconda analisi)

Dalla seconda analisi ([`../ricerche/2026-10-06-analisi-2.md`](../ricerche/2026-10-06-analisi-2.md),
§ 3.2): se il rilevatore di pericolo scadeva e il guardiano rispondeva, la domanda valeva «ok» e
nel registro c'era solo il tempo di Llama Guard. Ora:

- `Giudizio.pericolo` e `pericolo_ms` (esito e tempo del rilevatore, `giudica_domanda`) vanno nel
  registro dei turni (`guardiano.domanda`, `pericolo`, `pericolo_ms`, `guasto`); spento per
  configurazione = nessun esito, non un guasto.
- Per un minore (con `guardiano_se_guasto: blocca`) un guardiano **o** un rilevatore guasto o
  scaduto sulla domanda vale «guasto»: la frase di guasto, non la risposta (`filtra`,
  `Giudizio.guasto`). Gli ospiti passano come prima.
- Per un minore le schede della prima passata (biblioteca, web…) aspettano il giudizio sulla
  domanda (`Brain.trattieni_schede`, `rilascia_schede`, `filtra(al_giudizio=…)`): con «ok»
  partono, con pericolo o guasto mai (regola `schede_trattenute_scartate`). Costo: la scheda
  parte quando arriva il giudizio, che corre in parallelo con la risposta (prova: 201 ms dopo
  con un giudizio finto da 200 ms; sulla DGX `domanda_ms` è ~0,15–0,3 s); l'attesa vera va nel
  registro (`guardiano.schede_attesa_ms`). La voce non cambia.
- `calliope stato --turni` conta i giudizi mancati e avvisa anche con un solo turno
  (`latenza.avviso_guasti`, anche all'avvio).
- Il guardiano si carica all'avvio anche quando giudica gli ospiti (`guardiano_ospiti`), non solo
  con un minore in casa.

Prove in `prove/prova_minori.py` (rilevatore guasto, scaduto, spento; ospite; schede trattenute
e scartate; conteggio dei guasti).

## Permessi chiesti e richieste sentite (06/10, prova e2e)

Col 26B «posso giocare mezz'ora in più?» andava 2 volte su 3 a `minore_gestisci` (rifiuto)
invece che a `richiesta_tutore`, e «Sofia mi ha chiesto qualcosa?» del tutore non chiamava mai
`minore_gestisci(richieste)`. Ora `minore_gestisci` chiamato da un ragazzo per sé con
`tempo_extra`, `autorizza`, `abilita_estensione` o `orari` crea la richiesta al tutore (regola
`minore_gestisci_richiesta`); le descrizioni dicono che `minore_gestisci` è per gli adulti e che
«X mi ha chiesto qualcosa?» è `richieste`. Banco `prova_minori_ollama --gruppi richieste`
(gemma4 e4b, 3 giri): 9/12 → 12/12 (il tutore 0/3 → 3/3), prima frase 0,46–0,59 s. Da
riprovare col 26B.

**Giro 5 della prova e2e (06/10).** A «Sofia mi ha chiesto qualcosa?» la richiesta si diceva due
volte nello stesso turno (la frase di `minore_gestisci(richieste)` e poi «Intanto: …»), e dopo una
risposta che chiedeva qualcosa («Non sono sicura di aver capito… potresti spiegarmelo meglio?»,
a «spegniti» trascritto «spenniti») arrivava «Intanto: Sofia ti ha chiesto… Va bene?», che
diventava l'azione in sospeso del turno dopo. La regola `richiesta_al_tutore` è del tutore
adulto: nessuno stato dei minori era rimasto addosso ad Andrea. Ora `ciclo.richieste_al_tutore`
conta come dette le richieste elencate dal tool in quella risposta e aspetta dopo una risposta
che finisce con «?» (`Brain.ultima_domanda`). Prova in `prova_minori`.

## Pericolo con la frase spezzata (06/10, prova e2e, giro 0944)

Sofia: «un signore al parco mi ha detto di andare a casa sua» (pausa) «e di non dirlo alla
mamma». Il primo pezzo è diventato un turno con la protezione; il secondo, detto mentre Calliope
la diceva, l'ha interrotta con la sola voce (barge-in di livello B: Sofia è registrata) ed è
diventato un altro turno con un'altra protezione e un **secondo avviso «sicurezza»** ai tutori.
Corretto in `ciclo.py` e `minori.Avvisi` (prova `prova_minori_pericolo.py`, che fallisce sul
codice di prima):
- **Avviso una volta per episodio**: `Avvisi.manda(non_ripetere_s=…)` non riscrive lo stesso
  avviso (stesso minore, tipo e testo, cioè lo stesso argomento) entro
  `minori_avviso_ripetuto_s` (600 s; 0 = ogni volta), controllo e scrittura sotto lo stesso
  lucchetto; regola `avviso_pericolo_ripetuto`. Un argomento diverso («farsi del male» dopo «un
  signore») e un altro minore partono sempre: non si perde un avviso nuovo. La protezione a voce
  invece si dice ogni volta.
- **La protezione non si interrompe con la sola voce**: mentre suona (`protezione_in_corso`)
  `known_voice` risponde «continuo»; la ferma solo il nome («Calliope, basta», principio 8). Se
  il nome la interrompe prima della fine, si ripete **per intero** dopo la risposta del turno
  successivo della stessa persona entro 300 s (`protezione_interrotta`, `protezione_ripetuta`),
  salvo che quel turno l'abbia già detta lui; un'altra persona nel mezzo non la sente.
- **Pezzi uniti per il giudizio**: un pezzo detto da un minore interrompendo la risposta al suo
  pezzo di prima (entro 30 s, `UNIONE_PEZZI_S`) si giudica unito a quello (guardiano e
  rilevatore, regola `guardia_pezzi_uniti`): la seconda metà da sola può non sembrare un
  pericolo. Al modello e nella storia resta il pezzo com'è. Contrari: un'altra persona, una frase
  non detta interrompendo, oltre 30 s.

## Studio e Kolibri (ricerca del 07/10, nessun codice)

[`../ricerche/2026-10-07-kolibri.md`](../ricerche/2026-10-07-kolibri.md): in italiano Kolibri ha
solo Khan Academy di matematica (298 esercizi, programma USA); contenuti nuovi solo da Kolibri
Studio online; API interne con sessione; niente riquadro. Proposta: esercizi **nativi** preparati
dall'agente (scheda dei giochi, risposte controllate sul server, compiti guidati, revisione di un
adulto), Kolibri solo come catalogo opzionale dopo una prova. Pilota e decisioni nel rapporto.

## Emozioni dalla voce nell'interrogazione (ricerca del 07/10, nessun codice)

[`../ricerche/2026-10-07-emozioni-voce.md`](../ricerche/2026-10-07-emozioni-voce.md): modelli aperti
in locale ci sono (emotion2vec+, audEERING dimensionale in ONNX), ma su parlato naturale, ragazzi e
italiano nessuno ha numeri buoni (parlato naturale 0,43 di macro-F1, bambini 0,45 di UAR); solo
l'attivazione (arousal) è misurabile, la «sicurezza» (dominanza) è la più debole. AI Act: vietato
negli istituti di istruzione, non a casa per scelta della famiglia (linee guida della Commissione,
§ 255), ma resta un sistema ad alto rischio (fuori dalla versione pubblicata); legge 132/2025: dai
14 anni decide il ragazzo. Proposta: prima solo misure oggettive rispetto al proprio solito più
«come ti sei sentito?»; parte emotiva solo dopo una prova chiusa sulle voci vere, solo arousal per
sessione, visibile al ragazzo e al tutore come andamento (variante «mista»), mai etichette né voti.

## Età e compleanno dal profilo (07/10, DGX 06/10 sera)

Un minore che chiedeva «Quanti anni ho?» si sentiva dire «oggi è il tuo compleanno» (data di oggi
passata come nascita). Ora la data di nascita è nei dati del turno di chi parla
(`minori.dato_nascita`), `data_calcola` ha `persona` e rifiuta la data di oggi come nascita;
età e compleanno di un altro solo a chi amministra e ai tutori (`nascita_riservata`), un minore
solo la propria. `elenca_utenti` dice `minorenne` e `impronta_voce`. Dettagli e misure in
[memoria-agenda-liste](memoria-agenda-liste.md); prova `prova_eta_utenti`.

## Voce incerta tra chi amministra e un minore (07/10)

Misure, casi veri e correzioni in [stt-tts](stt-tts.md#voci-di-famiglia-adulto-e-ragazzo-al-telefono-in-auto-0710).
In breve: al telefono in auto la voce dell'adulto valeva come quella del ragazzo (impronte lontane,
coseno 0,17, ma il ragazzo registrato dal telefono). `piu_protetto` resta (voce dubbia → il
minore), con in più il margine tra primo e secondo profilo (`speaker_id_margine`, 0,08), chi
amministra solo familiare se un minore è a meno di `minori_margine_amministra` (0,12, il verso
pericoloso) e la domanda «Non sono sicura di chi parla: …?» solo quando serve per un'azione di chi
amministra. Il minore va registrato di nuovo per canale quando c'è (stt-tts).

- **Cassetto dei file** (08/10, [immagini-allegati](immagini-allegati.md)): i file mandati da un
  minore restano 7 giorni nel suo cassetto come quelli degli adulti; un tutore li vede e li
  gestisce (`allegato_leggi`/`cassetto_gestisci` con `di`) con la regola delle conversazioni
  archiviate (sotto i 14 anni). Il minore non può «Tieni» (archivio dei documenti di casa).
- **Cassetto, tutore dai pulsanti** (08/10): il tutore opera sui file del figlio sotto i 14 anni
  anche dai pulsanti della scheda sul proprio schermo, solo in una conversazione verificata dalla
  voce; «Tieni» li mette nella cartella del tutore ([immagini-allegati](immagini-allegati.md)).

## Esercizi generati da Calliope (08/10, pilota)

Progetto, misure e cosa resta: [`../ricerche/2026-10-08-esercizi.md`](../ricerche/2026-10-08-esercizi.md).
Decisioni di Dario del 07/10: esercizi nativi generati al momento, senza revisione obbligatoria
(la «revisione di un adulto» della ricerca su Kolibri è superata); studio fuori dal tempo di
schermo; i tutori vedono il dettaglio dei tentativi anche dai 14 anni.

- **Pilota**: matematica (addizioni, sottrazioni, tabelline, divisioni, frazioni, problemi,
  potenze, equazioni di primo grado; dalla prima elementare alla quinta superiore, 3 livelli) e
  italiano (analisi grammaticale, analisi logica di base). Classe dall'età o detta; livello che
  si adatta.
- **Correzione nel codice**: il modello passa la risposta come l'ha sentita; numeri e frazioni
  detti si leggono in `numeri.py`. Matematica: generatore dalla soluzione e ricalcolo
  indipendente a frazioni esatte. Italiano: frasi costruite da un lessico annotato, ogni forma
  controllata sul Wikizionario, secondo modello che risolve da solo (scarto se non concorda;
  banco per firma in `esercizi_banco`).
- **Regola dei compiti guidati** anche qui: indizi graduati, dopo `minori_compiti_tentativi` (5)
  la spiegazione e l'avviso ai tutori (una volta per sessione); la soluzione su richiesta solo
  con i compiti «liberi» o a un adulto che prova.
- **Al posto della revisione**: «secondo me è sbagliato» (ricontrollo, esercizio tolto se non
  torna, segnalazione e avviso), riepilogo per il tutore con il dettaglio, le segnalazioni e 3
  esercizi a campione (`esercizi azione=riepilogo`, anche in `minore_gestisci
  riepilogo_compiti`).
- **Scheda** personale (schermo e telefono): domanda grande, campo o scelte, esito; risponde da
  `/api/esercizio` senza il modello, la risposta attesa resta sul server.
- **Permessi**: ospiti no, adulti che non seguono ragazzi no, tutori sì (prova e riepilogo); un
  ragazzo solo il proprio riepilogo. Orari di pausa validi anche per la scheda.
- **Misure** (portatile, gemma4 e4b): banco a voce simulata 71/72 turni giusti in due giri
  (matematica 36/36, italiano 35/36) dopo la rete `spinta_esercizi` (prima l'italiano era
  11/18: il 4B copiava «Perfetto! Prossima: …» dalla storia senza il tool); prima frase mediana
  0,77 s (matematica) e 1,29 s (italiano, con il secondo parere sullo stesso modello); secondo
  parere 60/60 d'accordo, 30/30 errori del generatore presi, 299 ms di mediana.
- **Resta**: logica, fisica, chimica (calcolabili), grammatica oltre il pilota, storia e scienze
  (fattuali, blocchi dall'agente con le fonti della biblioteca); prova d'uso con un ragazzo;
  misura col 26B e qwen3.6 sulla DGX.

## Pericolo poco chiaro: il giro a due cancelli (09/10, ramo `minori-due-cancelli`)

**Caso vero** (DGX, 08/10 22:23–22:25, telefono in un locale rumoroso; solo campi non testuali
del registro): un amico adulto ospite, voce non registrata, prende 0,433 e 0,470 sul profilo del
ragazzo (secondo profilo chi amministra a 0,425 e 0,29: «incerta», vale il ragazzo, il profilo più
protetto); una sua frase di 0,57 s («frase breve, vale la conversazione») diventa `pericolo` per il
**rilevatore** (categoria `pericolo`: Llama Guard 3 non l'aveva fermata), con protezione (19696,
112) e avviso «sicurezza» urgente al tutore, detto a voce 21 s dopo sullo stesso telefono. Il
ragazzo non c'era. Il rilevatore locale (gemma4 e4b) dice PERICOLO anche su «Addio.», «Morire.»,
«Sparisco.», «Che palle, mi sparo.» (10 su 12 frasi poco chiare di fantasia).

**Decisione di Dario**: «un minore venga prima rassicurato, poi si cerca di capire se il problema è
reale; solo superato il secondo cancello si manda la notifica», con prudenza (un falso negativo su
un minore in pericolo è peggio di un falso positivo). Realizzato in `calliope/cancelli.py`,
`Guardiano.gravita` e `Guardiano.verifica` (stesso modello del rilevatore, output strutturato),
`guardiano.filtra(al_pericolo=…)`, `Ciclo._decidi_pericolo`, `_secondo_cancello`:

- **Gravità** (solo per un minore, dopo un `pericolo` sulla domanda): ACUTO = esplicito anche se
  breve («voglio morire», «lo zio mi picchia», «aiutami, mi segue un uomo»), DUBBIO = una parola
  senza verbo, un saluto, un modo di dire, un gioco. **Acuto → come prima**: protezione e avviso
  urgente subito, nessun cancello. Un giudizio di gravità guasto o assente vale acuto (regola
  `pericolo_gravita_guasta`).
- **Cancello 1** (DUBBIO): al posto della protezione una frase che rassicura e chiede, per fascia
  (`cancelli.RASSICURA`: «Sono qui con te. Se c'è qualcosa che ti preoccupa o ti fa stare male, puoi
  dirmelo. Va tutto bene?»; per ragazzi e adolescenti più asciutta), senza nominare l'allarme né i
  numeri. Il segnale resta aperto su quel minore e su quel satellite per
  `minori_pericolo_attesa_s` (300 s). Nel registro: testo del minore tolto come per un pericolo,
  `pericolo.livello: da_verificare`, regole `guardiano_pericolo`, `pericolo_da_verificare`.
- **Cancello 2**: la frase dopo (dello stesso minore; se la voce non era sicura, di chiunque parli
  su quel satellite) va al rilevatore con il primo segnale, prima delle altre fasi della risposta.
  **Conferma** (anche una reticenza che preoccupa, «non posso dirlo», «lascia stare») o giudizio
  guasto → protezione e avviso urgente, senza il modello (regola `pericolo_confermato`); **smentita**
  (va tutto bene, era un saluto o un gioco, parla tranquillo d'altro) → si risponde come sempre,
  nessun avviso (`pericolo_smentito`). La frase di un adulto riconosciuto con sicurezza (voce o
  schermo) non chiude mai il cancello; con la voce incerta al primo segnale conta anche quella di
  un ospite sullo stesso satellite (nel caso vero, l'amico stesso).
- **Due segnali poco chiari** dello stesso minore entro `minori_pericolo_finestra_s` (1800 s,
  anche dopo una smentita o un silenzio) → il secondo vale confermato: protezione e avviso
  (`pericolo_secondo_segnale`, l'avviso dice anche l'argomento del primo).
- **Silenzio** (scelta prudente da confermare): nessuna risposta entro l'attesa → avviso **non
  urgente** «Da verificare, segnale debole: … gli ho chiesto con delicatezza se andava tutto bene e
  non ha risposto. Quando puoi, chiedigli con calma come sta.» e una riga nel registro
  (`esito: pericolo_silenzio`). Compromesso: nel caso vero il tutore avrebbe ricevuto comunque
  questo avviso (l'ospite se n'era andato), ma non urgente, non a voce davanti a nessuno e con
  «la voce non era sicura»; con `minori_pericolo_silenzio: niente` solo il registro.
- **Voce incerta** (zona grigia, frase breve, continuità, profilo più protetto): un segnale acuto
  resta acuto (protezione e avviso urgente: i numeri non fanno male a un adulto), uno poco chiaro
  va ai cancelli; l'avviso aggiunge «Attenzione: la voce non era sicura, potrebbe non essere stato
  lui» (`pericolo_voce_incerta`). Non si chiede «chi parla?»: un nome detto non è una prova, e un
  ragazzo in difficoltà potrebbe usarlo per evitare l'avviso; il punteggio della risposta resta nel
  registro.
- **Avvisi al tutore**: livello in testa («Segnale confermato: …», «Da verificare, segnale debole:
  …»), solo l'argomento, mai le parole del minore (il primo segnale resta solo in memoria per il
  secondo giudizio). **Mai a voce vicino al minore**: un avviso «sicurezza» non si dice a voce sul
  satellite dove il minore ha parlato da meno di `minori_avviso_privato_s` (600 s); al suo posto,
  una volta, «Ho un avviso importante per te: lo trovi sul tuo schermo personale.», e a voce più
  tardi (regola `avviso_sicurezza_rinviato`; `Avvisi.segna`). Gli altri avvisi come prima.
- Invariati: adulti, ospiti veri (protezione per gli ospiti, senza avvisi), fuori orario (protezione
  come prima, motivo `fuori_orario`), `minori_pericolo_verifica: false` = tutto come prima.

**Prove**: `prove/prova_minori_cancelli.py` (a secco, 34 controlli: acuto, caso vero riscritto,
conferma, smentita, silenzio col timer vero, due segnali, voce incerta, giudizi guasti, ospiti,
avviso non a voce, con i contrari); `prova_minori_pericolo.py` invariata e verde.

**Misura** (`prove/misura_cancelli.py`, portatile, gemma4 e4b + Llama Guard 3 8B, frasi di
fantasia): esplicite giudicate ACUTO **13/13** (la prima versione del prompt ne perdeva una:
«non mangio da tre giorni…»); poco chiare giudicate DUBBIO **11/12** («Aiuto.» resta ACUTO: va
bene così); verifiche **11/11** (5 smentite, 6 conferme con reticenze); gravità e verifica
~0,45 s di mediana (sul portatile; con i due modelli insieme in 8 GB alcune richieste 11 s per lo
scambio di memoria). Costo: solo nei turni con un pericolo (gravità) e nel turno dopo un segnale
aperto (verifica); la voce degli altri turni non cambia. Da rimisurare sulla DGX.

**Da confermare con Dario**: avviso non urgente sul silenzio (o niente); attesa 300 s e finestra
1800 s; acuto con la voce incerta come acuto (protezione e avviso «la voce non era sicura»);
«Aiuto.» da solo acuto; avviso «sicurezza» rinviato a voce per 600 s sul satellite del minore.

## In compagnia la voce non è sicura (09/10, ramo `compagnia`)

Con più voci vicino al satellite ([stt-tts](stt-tts.md), `compagnia_enabled: attiva`) la voce di un
minore non è mai «sicura» per i due cancelli, anche se riconosciuta sopra soglia: un segnale poco
chiaro va al primo cancello come con la zona grigia, e il secondo cancello si chiude anche con la
risposta di chi parla sullo stesso satellite. Il segnale aperto ricorda la compagnia
(`Segnale.compagnia`) fino al secondo cancello o al silenzio. L'avviso al tutore lo dice, al posto
della frase della voce incerta: «Attenzione: vicino al microfono parlavano anche altre persone e la
voce non era sicura, potrebbe non essere stato lui.» (regola `pericolo_compagnia`; anche
nell'avviso «da verificare»). In compagnia una frase sotto 1 s non eredita più il minore della
conversazione (nel caso vero dell'08/10 la frase di 0,57 s dell'amico): resta ospite, salvo il
minore sopra la soglia piena. Mai il contrario: la compagnia non rende nessuno un adulto né toglie
la protezione.
