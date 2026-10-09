# Più persone che parlano: capire che le frasi sono di più voci (09/10/2026)

*Ramo `analisi-compagnia`. Analisi e misure, **nessuna modifica al codice di Calliope**. Aree:
[stt-tts](../aree/stt-tts.md) (chi parla), [contesto-conversazione](../aree/contesto-conversazione.md)
(conversazione per persona, finestra d'ascolto), [voce-e-regole](../aree/voce-e-regole.md)
(principio 10), [minori](../aree/minori.md) (profilo più protetto, guardiano, due cancelli).
Script manuali, non nel runner: `prove/misura_voci_compagnia.py` (impronte CAM++) e
`prove/misura_rivolta.py` (giudizio del modello). Dati veri: dal registro dei turni della DGX
(02–09/10, 1158 frasi con la voce) **solo i numeri** dei campi `voce` (migliore, punteggio,
secondo, modo, durata), esito, regole, finestra d'ascolto e satellite; persone e satelliti con
etichette (A1 = chi amministra, M1 = il minore, tel1 = il telefono, sat2 = lo studio); nessun
testo. Le frasi della misura del modello sono di fantasia.*

## 1. La domanda e il caso vero

Dario (09/10): «Può capitare di parlare con amici o estranei mentre Calliope è in ascolto. Come
possiamo dedurre che le frasi sono di più di una persona?»

**Caso vero** (DGX, satellite telefono in un locale rumoroso, con un amico):

- **08/10, 22:22–22:25.** Due frasi di ~1 s dell'amico prima che Dario parli: ospite, punteggio
  0,13 e 0,12 sul profilo di Dario (lontanissime). Poi Dario riconosciuto (0,69–0,72). Alle
  22:23:11 una frase di 2,8 s dell'amico prende **0,433 sul minore e 0,425 su Dario**: voce
  incerta, vale il minore (`minore_piu_protetto`), la frase chiede chi parla
  (`voce_incerta_chiede`). Alle 22:24:13 (2,9 s) **0,47 sul minore**, 0,29 su Dario: vale il
  minore, la conversazione di Dario si chiude (`conversazione_altra_persona`), preset del minore.
  Alle 22:24:24 una frase di 0,57 s «breve, vale la conversazione» (cioè il minore): il rilevatore
  la prende per pericolo (`guardiano_pericolo`) e parte l'avviso al tutore. Il ragazzo non c'era.
- **09/10, 01:29–01:45.** 45 frasi: 17 di Dario riconosciute (0,50–0,76), **23 non
  riconosciute**, di cui **20 dentro la finestra d'ascolto** (senza il nome), 18 con una
  risposta. Sei frasi lunghe (4,9–14,3 s) stanno a **0,22–0,33** su Dario, mentre le sue frasi di
  quella notte stanno sopra 0,49: un'altra voce, quasi certamente. Calliope risponde anche a frasi
  non rivolte a lei («Non lo portavo in giro» → «non sto parlando con te»).

**La catena della finestra d'ascolto.** Dopo ogni risposta il microfono resta aperto
`followup_s` (8 s) senza bisogno del nome. In compagnia chiunque parli in quegli 8 s viene
trascritto e riceve una risposta, e la risposta riapre la finestra: nei due episodi 66 frasi su 75
sono arrivate dentro la finestra, e 20 delle 23 frasi di ospiti dentro la finestra hanno avuto una
risposta. Sul registro intero, 97 delle 153 frasi non riconosciute sono arrivate senza il nome
(78 con una risposta). È la causa principale del «risponde a chiunque», più dell'identificazione.

## 2. Cosa c'è oggi

| Meccanismo | Dove | Con più persone |
|---|---|---|
| Impronta CAM++ di ogni frase (192 numeri), calcolata in parallelo a Whisper | `ciclo.py` (`emb_job`), `speaker_id.SpeakerEmbedder` | Confrontata **solo con i profili registrati**; due ospiti diversi sono entrambi «nessuno» |
| Soglia 0,48, zona grigia 0,42 se era chi parlava, margine 0,08 sul secondo profilo | `ciclo._confronta_voce` | Al telefono le voci si comprimono: l'amico a 0,43 sul minore e 0,43 su Dario |
| Frase breve (< 1 s, nella finestra): vale chi parlava, al più familiare | idem (`how = "breve"`) | Il «sì» o il saluto dell'amico valgono come chi parlava prima (anche il minore attribuito per prudenza: 22:24:24) |
| Continuità (frase cortissima di chi è stato riconosciuto qui da 15 min, ≥ 0,36, margine 0,20) | `ciclo._per_continuita` | `_ricorda_voce` la toglie già se arriva una frase lunga di un'altra persona: il primo, timido, «c'è un'altra voce» |
| Profilo più protetto: un minore almeno in zona grigia vale il minore | `minori.piu_protetto` | Un adulto ospite con la voce vicina al minore diventa il minore: preset, guardiano, avviso |
| Una conversazione per persona; ospiti nella conversazione anonima del satellite; chi cambia chiude la conversazione (`conversazione_altra_persona`) | `corsie.RegistroConversazioni.scegli`, `brain` | Funziona: gli ospiti non entrano nella storia di Dario; ma si alternano con Dario e ogni cambio chiude e riapre |
| Impronte delle frasi recenti **in memoria**, per riconoscere i doppioni tra satelliti | `corsie.RegistroConversazioni._recenti` | Precedente utile: vettori solo in memoria, per pochi secondi, mai su disco |
| Registro dei turni: nome, migliore, punteggio, secondo, margine, modo, durata; degli ospiti nessun testo | `turnlog.py`, `ciclo._riconosci_voce` | Nessuna impronta (giusto), nessun numero sulle voci tra frasi |

Le impronte delle frasi **non vengono tenute** oltre il turno (salvo i doppioni, per pochi
secondi). Per il punto 1 della proposta servono: le ultime frasi di ogni satellite per qualche
minuto, **solo in memoria**, come già i doppioni. Una frase costa 768 byte; i confronti sono
prodotti scalari (microsecondi).

## 3. Misure

### 3.1 Due frasi tra loro (misura A)

Coseno tra le impronte di due frasi della stessa persona o di persone diverse. Corpus: MLS e
VoxPopuli italiano (61 voci, stesso canale tra loro), 10 voci Piper, 240 frasi di Dario dalle
registrazioni del portatile (sei giorni e tre microfoni diversi; escluse le cartelle del 26/09,
dove ci sono altre voci e la TV). Esclusi due «parlanti» del corpus che sono più voci (etichette
sbagliate del corpus, non errori dell'impronta).

| Durata | Stessa persona (corpus) p5 / mediana | Dario p5 / mediana | Persone diverse mediana / p95 |
|---|---|---|---|
| 1,5 s | 0,36 / 0,56 | 0,24 / 0,41 | 0,13 / 0,32 |
| 2 s | 0,43 / 0,64 | 0,30 / 0,50 | 0,14 / 0,33 |
| 3 s | 0,49 / 0,72 | 0,40 / 0,60 | 0,15 / 0,35 |

Una frase contro **una** frase separa male: a 2 s, con il taglio a 0,20 la stessa persona finisce
sotto lo 0,5 % delle volte, ma due persone diverse restano sopra il 29 % delle volte. Dario
(microfoni e giorni diversi) è più disperso del corpus: la «persona sola con la voce variabile»
è reale, sotto i 2 s soprattutto (a 1,5 s il 15 % delle sue coppie sta sotto 0,30).

### 3.2 Una frase contro il profilo di chi è stato riconosciuto (misura B)

Profilo = media di 5 frasi (per Dario: 5 frasi di una sessione, prova sulle altre sessioni).

| Durata | Dario sotto 0,20 / 0,25 | Altre voci (canale diverso) sotto 0,20 / 0,25 | MLS: stessa sotto 0,20 / 0,25 | MLS: altre (stesso canale) sotto 0,20 / 0,25 |
|---|---|---|---|---|
| 1,0 s | 0 / 2,2 % | 90 / 98 % | 0,5 / 0,5 % | 73 / 86 % |
| 1,5 s | 0 / 0 % | 86 / 95 % | 0,5 / 0,5 % | 69 / 84 % |
| 2,0 s | 0 / 0 % | 85 / 94 % | 0,3 / 0,5 % | 66 / 82 % |
| 3,0 s | 0 / 0 % | 79 / 90 % | 0,5 / 0,5 % | 63 / 80 % |

Contro un profilo il segnale è molto più pulito: **una frase di almeno 1 s sotto 0,20–0,25 sul
profilo di chi è stato riconosciuto da poco è quasi sempre un'altra voce** (stessa persona sotto
0,20: ≤ 0,5 %; sotto 0,25: ≤ 2,2 %), e la si vede in 2 casi su 3 anche con il canale uguale. Il limite è il contrario:
un'altra voce **simile** o compressa dal canale resta sopra (l'amico al telefono stava a 0,29–0,43
su Dario nelle frasi lunghe dell'08/10, e a 0,12–0,13 in quelle di 1 s).

### 3.3 Gruppi di voci in linea (misura C)

Simulazione di una sessione sullo stesso satellite con le **durate delle frasi vere** della DGX
(< 1 s 24 %, 1–1,5 s 12 %, 1,5–2 s 13 %, 2–3 s 18 %, 3–4 s 9 %, ≥ 4 s 24 %). Ogni frase utile
(≥ `dmin`) entra nel gruppo col centroide più vicino se il coseno è ≥ τ, altrimenti apre un
gruppo; «compagnia» = due gruppi confermati (due frasi, o una frase ≥ 3 s). Una voce sola: 10
frasi; due voci: 6 + 3 in ordine casuale.

| τ | dmin | conferma | Falsa compagnia, una voce (MLS / Dario) | Due voci rilevate (se la seconda ha detto una frase utile) |
|---|---|---|---|---|
| 0,20 | 1,5 s | frase ≥ 3 s | 2,6 / 0,2 % | 60 % |
| 0,25 | 1,5 s | frase ≥ 3 s | 2,0 / 0,6 % | 70 % |
| 0,30 | 1,5 s | frase ≥ 3 s | 1,8 / 1,8 % | 82 % |
| 0,25 | 1,5 s | due frasi | 1,0 / 0,2 % | 59 % |
| 0,30 | 1,5 s | due frasi | 0,4 / 0,8 % | 64 % |
| 0,30 | 2,0 s | due frasi | 0,0 / 0,0 % | 46 % |

Partire dal profilo di chi è registrato come primo gruppo non cambia molto (stessi numeri ±5
punti). Le falsi compagnie di una voce sola sono **rare** (≤ 2,6 % delle sessioni MLS, ≤ 1,8 % di
Dario tra giorni e microfoni diversi); il rilevamento di un amico che dice 3 frasi è
**incompleto** (46–82 %): spesso dice frasi troppo corte o la sua voce cade nel
gruppo dell'altro. Il gruppo tra frasi serve soprattutto **tra ospiti** (due ospiti diversi, che
oggi sono entrambi «nessuno»); quando c'è una persona registrata, la misura B fa meglio e costa
uguale.

### 3.4 Due voci dentro una frase (misura D)

Frasi miste (A per 2–4 s, 0,3 s di pausa, B per 1,5–3 s, stesso corpus) contro frasi di una voce
(due frasi della stessa persona incollate, o una frase lunga), divise in finestre con
sovrapposizione a metà; statistica = coseno minimo tra due finestre.

| Finestra | Taglio | Frasi miste prese | Una voce, due frasi incollate (falsi) | Frasi lunghe di Dario (falsi, 20) |
|---|---|---|---|---|
| 1,5 s | < 0,10 | 59 % | 0,7 % | 0 % |
| 1,5 s | < 0,20 | 80 % | 3,3 % | 0 % |
| 2,0 s | < 0,20 | 54 % | 0,7 % | 0 % |

**Costo di CAM++** (CPU del portatile, `speaker_threads` 2 / 4): 45 / 37 ms per una finestra di
1,5 s, 52 / 45 ms per 2 s, 126 / 133 ms per 5 s, 214 / 222 ms per 10 s. Una frase di 10 s in
finestre di 1,5 s sono ~12 finestre: ~0,5 s di CPU (sulla DGX ARM da misurare). Si può fare in
parallelo a Whisper, ma il segnale è incerto: a un falso su 30 (due frasi della stessa persona incollate) si prende
4 frasi miste su 5, e il corpus è voce letta e pulita; un'interiezione breve in un locale
rumoroso è un'altra cosa (in una prova precedente, con un'altra estrazione casuale, un'interiezione
di 1,5 s si vedeva una volta su tre). Non vale il costo oggi.

### 3.5 Il registro vero (02–09/10): quante frasi sarebbero «in compagnia»

Il registro non ha le impronte, quindi la regola si prova nella forma della misura B, che usa solo
i punteggi: **sullo stesso satellite, negli ultimi 5 minuti, una persona riconosciuta dalla voce e
una frase di almeno 1 s (non sua) con meno di 0,20 sul suo profilo, oppure due persone
registrate diverse** (in qualunque ordine).

- **167 frasi su 1158 (14 %)** sarebbero state in compagnia; con il taglio a 0,25: 198 (17 %);
  con 1,5 s minimi e 0,25: 161 (14 %), ma l'episodio dell'08/10 sfugge (le frasi lunghe
  dell'amico stavano a 0,29–0,43 su Dario).
- **08/10**: in compagnia dalle 22:22:31 (la prima frase di Dario dopo le due di ~1 s
  dell'amico a 0,12–0,13), **prima** della voce incerta delle 22:23:11 e del falso allarme delle
  22:24:24. **09/10**: dalle 01:30:38, la prima frase lunga dell'amico (0,18 su Dario).
- Gli altri giorni presi: telefono 06–07/10 (in auto con il minore: compagnia vera, è il caso
  delle «Voci di famiglia») e 05/10 sera (25 frasi), studio 06/10 (12 frasi), e il 02–05/10 prima
  che il registro avesse il satellite (57 frasi, 40 la mattina del 03/10). **Da confermare con Dario** se in quei momenti c'era davvero
  qualcun altro (o la TV): è l'unica verità che il registro non ha.
- Nelle 167 frasi: 147 senza il nome (finestra d'ascolto), di cui **65 di ospiti**: sono le frasi
  che il punto 3 dovrebbe giudicare. 24 frasi brevi o in zona grigia di una persona perderebbero
  la continuità (5 con un tool: `delega_lavoro` ×2, `casa_stato`, `data_calcola`,
  `pc_cerca_file`).

### 3.6 «È rivolta a me?» col modello (misura E)

`gemma4:e4b-it-qat` sul portatile (lo stesso modello del rilevatore di pericolo sulla DGX), 56
frasi di fantasia dentro la finestra d'ascolto con il turno prima: 27 rivolte a Calliope (seguiti,
«sì», «grazie», un ospite che le parla, comandi con un'altra persona dentro: «Ricorda che a
Giulia…», «Manda un messaggio a Giulia…», i **contrari**) e 29 no (chiacchiere, Calliope in terza
persona, un altro nominato come interlocutore, «Chiedile se…», «Dille alle sette…»).

| Modo | Rivolte giuste | Non rivolte giuste | Tempo mediano |
|---|---|---|---|
| Giudizio separato (JSON `{"per_calliope"}`), senza l'indizio della voce | 26 / 27 | 27 / 29 | 285 ms |
| Giudizio separato, con «voce non registrata, diversa da Marco» | 26 / 27 | 27 / 29 | 283 ms |
| Risposta stessa con «[silenzio]», senza l'indizio | 25 / 27 | 25 / 29 | 240 ms |
| Risposta stessa con «[silenzio]», con l'indizio | 18 / 27 | 29 / 29 | 226 ms |

- Il **giudizio separato** è il migliore: 53 su 56. Errori: «Che ne pensi dei cani?» (ospite,
  davvero ambigua) preso per non rivolto; «Dille alle sette, che domani lavoriamo.» e «Ok.» presi
  per rivolti. L'indizio della voce non cambia nulla.
- **Dentro la risposta** il modello sbaglia di più, e con l'indizio della voce diventa sordo
  (9 frasi rivolte a lei zittite, 6 di Marco: «E dopodomani?», «Grazie.», «Spostala alle
  undici.»): da scartare.
- Sulla DGX il modello della voce è il 26B; il giudizio separato va bene sul modello piccolo che
  è già caricato (il rilevatore), con una richiesta di ~250 token e ~8 in uscita. Va rimisurato
  sulla DGX con le frasi vere (in ombra).

### 3.7 Latenza

- **Gruppi e profilo (punti 1 e 4)**: zero. L'impronta della frase si calcola già, in parallelo a
  Whisper; il resto sono prodotti scalari.
- **Finestre dentro la frase (punto 2)**: 37–52 ms per finestra su CPU, ~0,5 s per una frase di
  10 s; in parallelo a Whisper si nasconde in parte. Non proposto ora.
- **Giudizio «rivolta» (punto 3)**: ~0,28 s sul portatile. In parallelo alla risposta (prima
  frase sulla DGX: mediana 2 s il 05/10), aggiunge zero se si aspetta il giudizio solo **prima di
  dire la prima frase e prima di eseguire un tool**; e scatta solo in compagnia, dentro la finestra
  e senza il nome (65 frasi su 1158 nel registro).

## 4. La proposta, punto per punto

**1. Più voci tra frasi: sì, in due forme.** (a) **contro il profilo** di chi è stato riconosciuto
dalla voce su quel satellite negli ultimi minuti (misura B: τ 0,20, frasi ≥ 1 s): il segnale
migliore, prende entrambi gli episodi veri prima del danno; (b) **gruppi tra frasi** per le voci
senza profilo (misura C: τ 0,25–0,30, frasi ≥ 1,5 s, gruppo confermato da due frasi o da una di
3 s): rileva due ospiti diversi, falsi rari. Regola sull'audio (principio 10, «ciò che il modello
non vede»), con il nome `voci_compagnia` nel registro. Impronte solo in memoria, per corsia, per
`compagnia_finestra_s` (300 s), mai su disco né nel registro (nel registro: numero di voci, la
prova che ha deciso, la distanza; come per i doppioni). Due persone registrate diverse riconosciute
sullo stesso satellite contano da sole (in auto con il minore).

**2. Due voci dentro una frase: no per ora.** Misura D: si vedono 6–8 frasi miste su 10 con lo 0,7–3 % di
falsi su voce letta e pulita, meno le interiezioni brevi, e ~0,5 s di CPU per le frasi lunghe. Da riprendere
solo se l'ombra (F0) mostra frasi lunghe con il punteggio crollato sul profilo di chi parlava (il
segno di una frase mista) in numero che conta.

**3. A chi è rivolta la frase: sì, ma solo in compagnia, solo senza il nome, con un giudizio
separato.** Il significato lo decide il modello (principio 10), non una regola sulle parole («nomina
un'altra persona» sbaglia proprio sui contrari: «Ricorda che a Giulia piace la pizza»). Se il
giudizio dice no: silenzio, **niente nuova finestra** (spezza la catena del § 1), regola
`non_rivolta` nel registro con il tempo del giudizio. Errore tipico in sicurezza: una frase
giudicata non rivolta si ripete col nome; nessun guadagno per chi volesse abusarne (si può solo
far tacere Calliope). Gli indizi della voce non servono al giudizio (§ 3.6) e non vanno nel prompt.

**4. Modalità compagnia: sì, con effetti stretti e reversibili.** Quando 1 vede ≥ 2 voci negli
ultimi `compagnia_finestra_s`:

- **Finestra d'ascolto**: una frase senza il nome passa solo se il giudizio del punto 3 dice
  «rivolta» (con il nome: come sempre). Più leggero di «nome a ogni frase», che toglierebbe i
  seguiti anche a Dario (molti nei due episodi) e che si può tenere come opzione.
- **Niente frase breve né continuità**: sotto `speaker_min_voice_s` una frase non eredita chi
  parlava (in compagnia non si sa chi è): ospite, salvo il minore se lo supera la soglia piena come
  oggi. Niente conferma breve: per le azioni di chi amministra la frase di sfida. Costo misurato: 24
  frasi su 167 in compagnia, 5 con un tool.
- **Chi parla nella frase per le azioni**: le azioni che chiedono un livello (familiare o più)
  vogliono la voce riconosciuta **in quella frase** (`modo = voce`); la zona grigia vale ospite.
- **Minore per prudenza: resta**, ma l'informazione «in compagnia» va al giro a due cancelli (in
  sviluppo, ramo `minori-due-cancelli`): in compagnia un segnale di pericolo attribuito a un
  minore per voce incerta conta come **voce non sicura**, quindi cancello 1 (rassicurare e
  chiedere) e non l'avviso urgente, salvo i segnali acuti; l'avviso, se parte, dice «eravate in
  compagnia, potrebbe non essere stato lui». Sull'08/10 la frase di 0,57 s sarebbe stata un ospite
  (niente «breve» in compagnia, 0,35 sul minore è sotto la zona grigia): niente preset del minore,
  niente avviso.
- **Segno sullo schermo** del satellite («in compagnia»), e nella console.
- **Ritorno**: nessuna prova di un'altra voce per `compagnia_finestra_s` (5 minuti). Niente comando
  a voce per uscirne (un ospite potrebbe dirlo).

Ciò che la compagnia **non** fa: non cambia soglie, margini né la scelta del profilo più protetto;
non rende mai una voce incerta un adulto; non abbassa nessuna protezione. Aggiunge solo richieste
e silenzi.

## 5. Rischi

- **Una persona sola con la voce variabile** (raffreddore, stanchezza, microfono diverso): sul
  portatile Dario non va mai sotto 0,25 sul suo profilo con frasi ≥ 1 s (misura B) e non crea gruppi
  falsi (≤ 0,4 % delle sessioni). **Il telefono è il punto debole**: le frasi lunghe di Dario al
  telefono hanno p5 0,37 sul profilo (contro 0,58 dello studio), e il 09/10 una frase lunga non
  riconosciuta stava a 0,23 senza che si sappia se era sua. La TV e la radio creano compagnia: è il
  comportamento giusto (non vanno ascoltate), ma va contato nell'ombra.
- **Telefono in auto con margini stretti** (0,07–0,16 tra adulto e minore): la compagnia non tocca
  quei margini; in auto con il minore è compagnia vera, e i suoi effetti (niente «breve», più
  sfide) sono quelli giusti. Costo: più domande «chi parla?» per Dario in auto.
- **Ospite simile a una persona registrata** (l'amico a 0,43 sul minore): né i gruppi né il profilo
  lo distinguono dal minore in una frase sola; la compagnia non lo cambia (prudenza), cambia solo
  ciò che succede dopo (due cancelli, avviso con il dubbio).
- **Seguiti persi**: un «E domani?» di Dario giudicato non rivolto (1 su 27 nella misura) va ripetuto
  col nome. In compagnia è accettabile; fuori dalla compagnia il giudizio non scatta mai.
- **Privacy**: impronte delle frasi di ospiti tenute per 5 minuti in memoria. Sono vettori senza
  testo, per corsia, e spariscono con la finestra o al riavvio; nel registro solo numeri. Nessuna
  impronta di ospite diventa mai un profilo.

## 6. Raccomandazione a fasi

**F0 — ombra (nessun effetto), una settimana.** `calliope/compagnia.py` con
`Compagnia.osserva(corsia, impronta, voce_s, nome, modo)` → stato per corsia (voci, prova,
distanza); in `ciclo._riconosci_voce` dopo il riconoscimento. Nel registro `voce.compagnia =
{"voci": n, "prova": "profilo"|"gruppi"|"due_profili", "distanza": x}` e la regola
`voci_compagnia` (solo nome). Nella stessa fase il giudizio del punto 3 **in ombra** sulle frasi
senza il nome in compagnia (`rivolta: {per_calliope, ms}` nel registro, nessun effetto), sul modello
del rilevatore. Configurazione: `compagnia_enabled` (ombra / attiva / spenta),
`compagnia_finestra_s` 300, `compagnia_soglia_profilo` 0,20, `compagnia_voce_min_s` 1,0,
`compagnia_soglia_gruppi` 0,25, `compagnia_gruppi_min_s` 1,5. Prove a secco
(`prove/prova_compagnia.py`, impronte sintetiche come `prova_voci_famiglia`): i due episodi veri
in numeri; contrari: una voce sola con frasi a 0,25–0,35, frasi < 1 s, una persona riconosciuta su
un altro satellite, finestra scaduta, due ospiti uguali, due ospiti diversi, due profili diversi,
la TV a 0,1. Rilettura: Dario dice quali momenti erano davvero in compagnia; si tarano le soglie.

**F1 — effetti sull'identità** (dopo l'ombra): niente frase breve né continuità né conferma breve
in compagnia (regola `compagnia_senza_breve`), azioni solo con la voce nella frase, segno sullo
schermo, informazione ai due cancelli (`compagnia` come voce non sicura). Prove: quelle di
`prova_voci_famiglia` e `prova_minori_cancelli` con la compagnia accesa e spenta.

**F2 — la finestra d'ascolto in compagnia**: il giudizio del punto 3 decide; se «non rivolta»,
silenzio senza nuova finestra (regola `non_rivolta`). Giudizio in parallelo alla risposta, atteso
solo prima della prima frase e dei tool. Prova col modello (`prove/misura_rivolta.py` diventa una
prova con le soglie: ≥ 25/27 rivolte, ≥ 26/29 non rivolte, sul modello del rilevatore) e i
contrari nella prova a secco del ciclo (il nome sempre passa; fuori dalla compagnia il giudizio non
scatta).

**F3 — se servono**: gruppi di ospiti come identità (un ospite con la sua conversazione anonima
distinta da un altro ospite sullo stesso satellite); finestre dentro la frase (punto 2); più
impronte per canale (già valutato nelle «Voci di famiglia») che risolve la radice del telefono.

## 7. Cosa resta e domande per Dario

- **Verità dei momenti**: nei giorni 02–07/10 il registro vede compagnia in 14 % delle frasi
  (telefono il 05/10 sera e in auto con il minore il 06–07/10, studio il 06/10 alle 18:01, mattina
  del 03/10). Erano
  davvero con qualcuno, o c'era la TV? Serve a tarare F0.
- **«Nome a ogni frase» o giudizio?** La misura dice che il giudizio separato tiene i seguiti di
  Dario (26/27) e taglia le chiacchiere (27/29); il nome a ogni frase è più semplice e sicuro ma
  toglie tutti i seguiti in compagnia. Da scegliere.
- **Misure da rifare sulla DGX**: CAM++ per finestra sulla CPU ARM; il giudizio col modello del
  rilevatore e con il 26B, con le frasi vere dell'ombra.
