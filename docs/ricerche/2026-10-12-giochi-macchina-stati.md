# La macchina a stati dei giochi fornita da Calliope: progetto (12/10/2026)

*Progetto scritto, chiesto da chi amministra il 12/10. Nessuna modifica al codice di produzione:
i prototipi usa e getta (motore delle fasi, esploratore, forme con uno slot, giudice di fase,
palco con il controllo «fuori dal palco») sono nella cartella temporanea della sessione, fuori dal
repository. Fatto sul codice di `main` a d6caa62. Fonti: [giochi](../aree/giochi.md),
[agenti-estensioni](../aree/agenti-estensioni.md), [`2026-10-05-giochi.md`](2026-10-05-giochi.md),
[`2026-10-10-macchina-stati.md`](2026-10-10-macchina-stati.md) (lo stato del dialogo), la sezione
«Macchina a stati dei giochi» dell'analisi del flusso del 12/10 (fuori dal repository).*

## La richiesta

Parole di chi amministra, riassunte: un gioco per Calliope deve gestire al meglio i comandi
vocali. Un'estensione è come un tool (una chiamata, un risultato); un gioco è interattivo e fatto
di **fasi**. Calliope dà **a priori** una macchina a stati del gioco, sempre disponibile, così
l'agente che scrive il gioco non ci deve pensare e fa meno confusione. Tutto sta in **pagine
ridisegnabili senza scroll**.

Vincoli già decisi:
- **niente compatibilità** con i giochi già approvati (Calliope è in prova: si possono rompere);
- ogni funzione dichiara come si comporta nel **profilo ridotto da 8 GB** di VRAM;
- i giochi in **tempo reale o senza turni** hanno una via libera, per eccezione.

## In breve

**Raccomandazione.** Il gioco diventa una **dichiarazione** più una **logica pura**. Nel
manifesto la scheda ha una sezione `macchina`: fasi, comandi per fase (con un eventuale parametro,
«porta {n}» con un dominio chiuso), pagina di ogni fase e fasi verso cui si può andare. In
`logica.js` l'agente scrive solo funzioni pure: la partita nuova, le mosse per fase e comando,
quali comandi (e valori) valgono adesso, cosa mostrare. Il resto è di Calliope, nel **motore** che
gira nel riquadro prima del codice del gioco. Il motore tiene lo stato della partita, ha le fasi
standard (preparazione con il numero e i nomi dei giocatori, turno, esito della mossa, fine con
classifica e «ancora»), disegna le pagine sul palco fisso, fa di ogni comando un pulsante e manda a
Calliope un'**istantanea** numerata dopo ogni mossa.

- **Un solo scrittore dello stato**: il motore nel riquadro. Il server tiene una copia
  (l'istantanea), validata contro il manifesto; ogni comando a voce porta il numero
  dell'istantanea su cui è stato riconosciuto, e un comando vecchio si rifiuta. Così lo stato del
  gioco e quello di Calliope non divergono per costruzione: Calliope non calcola niente del
  gioco, lo legge.
- **Lo slot è un'abbreviazione di un elenco.** «porta {n}» con n tra le porte chiuse si espande
  nelle forme intere «porta 1», «porta 3», … sul dominio **di adesso**: il principio 10 resta vero
  alla lettera (insieme di frasi finito, confronto per intero). Il prototipo riconosce 15 frasi su
  15 (5 buone, 10 contrarie: «porta 37», «la porta due» già aperta, «chiudi la porta», «la porta
  tre per favore»…), in 0,8 ms con 401 forme.
- **La via di mezzo** per le frasi libere: un **giudice di fase**, una chiamata breve e separata
  allo stesso modello già in memoria, con l'uscita vincolata a un elenco chiuso (i comandi della
  fase espansi, più «nessuno»). Misurato sul portatile con gemma4 e4b, il modello del profilo da
  8 GB: **21 giuste su 22, mediana 357 ms, p90 386 ms**, nessuna VRAM in più, e la cache del
  prompt della voce resta intatta. La prima formulazione del prompt diceva sempre «nessuno»
  (12/22): la forma del prompt conta, e va nelle prove col modello.
- **Calliope sa a che punto è il gioco** dall'istantanea: «a chi tocca?», «quanti punti ho?», «chi
  vince?» sono forme chiuse standard di ogni fase, con la risposta composta dal codice; le altre
  domande vanno al modello con l'istantanea nei dati del turno (circa 60 token).
- **Pagine**: palco fisso **1280×720** in orizzontale e **720×1280** in verticale (telefono),
  scalato e centrato, mai scroll. Sei modelli di pagina scritti da Calliope (titolo, scelte,
  griglia, messaggio, punteggi, classifica), più la «tela» per l'eccezione. Il tema sono variabili
  CSS in `tema.css`: si ridisegna senza toccare la logica. Il testo si adatta (si rimpicciolisce
  fino a un minimo) e il motore **misura** dopo ogni disegno: niente fuori dal palco, niente testo
  tagliato. Il prototipo in Edge senza finestra trova i due difetti messi apposta, a quattro
  misure di finestra, in 0,8–1,1 s per misura.
- **La prova di fumo per fasi** percorre la macchina dichiarata, prova ogni comando con ogni
  valore, trova le fasi senza uscita e quelle mai raggiunte, gioca partite intere fino alla
  fine. Prototipo: 5000 stati in 52–78 ms; sul gioco con una fase «bonus» senza uscita dice «fase
  «bonus» senza uscita: nessun comando attivo (strada: inizia → porta 2)».
- **L'agente scrive meno**: lo scheletro nuovo è di circa 540 token (oggi 657) e non ha DOM,
  `sicuro()`, `comandiAttivi` né turni e punti fatti a mano.

**Piano** in otto passi piccoli (§ 10), ognuno con le sue prove, circa 9 giorni di lavoro più un
giro vero sulla DGX. **Domande aperte** per chi amministra in § 11; il profilo da 8 GB funzione per funzione in § 9.

## 1. Com'è oggi

- Un gioco è `logica.js` + `gioco.js` liberi nel riquadro (`<iframe sandbox="allow-scripts">`,
  origine opaca, CSP senza rete), con l'oggetto `calliope` del runtime (`scheda.RUNTIME_JS`). Il
  disegno, i turni, i punti, i nomi dei giocatori e la fine li scrive l'agente, ogni volta da
  capo.
- I comandi a voce (11/10 sera) sono un elenco **piatto** nel manifesto (`scheda.ascolta`: al più
  24 comandi, forme intere fisse); il gioco dice a runtime quali valgono
  (`calliope.comandiAttivi`) e riceve la mossa con `calliope.quandoComando`. La regola
  `gioco_comando` del ciclo (`Ciclo._comando_gioco`) confronta la frase intera
  (`gioco_voce.trova`); nella finestra del gioco senza nome passa solo l'elenco
  (`gioco_finestra_ignorata`); le frasi diverse vanno al modello della voce, che ha il tool
  `gioco_comando`.
- Calliope non sa niente della partita: non sa a chi tocca né i punti, e non sa in che fase è.
  Sa solo quali comandi valgono adesso.
- Il caso vero dell'11/10 (Halloween, 45 minuti a vuoto) è nato quasi tutto in parti che non sono
  il gioco: costanti doppie tra i due file, un'eccezione della logica uscita dal gestore di
  «Inizia» (i nomi vuoti della preparazione), il disegno riscritto nove volte. La preparazione con
  i nomi era proprio il punto dove l'agente ha sbagliato.
- La pagina del riquadro scorre se il gioco non ci sta (`_STILE_BASE`, `overflow:auto`); nessuno
  controlla che un gioco stia nello schermo, e la prova di fumo ha un DOM finto senza
  impaginazione.

## 2. Fasi e dichiarazione

### 2.1 Le fasi standard di Calliope

| Fase | Cosa fa il motore | Comandi standard (forme chiuse) | Cosa può aggiungere il gioco |
|---|---|---|---|
| `preparazione` | quanti giocatori (tra `giocatori.min` e `max`), i nomi, poi la prima fase del gioco | «{n} giocatori», «siamo in {n}», «{n}»; «gioco anch'io», «anch'io»; «inizia», «via» | opzioni chiuse (livello, numero di porte) come comandi con un dominio |
| `turno` | «Tocca a …», giro dei turni, punteggi in fascia | quelli del gioco | i comandi della mossa (e la logica) |
| `esito` | il messaggio della mossa e i punti guadagnati; poi la fase indicata dalla mossa (`dopo`) | «avanti», «continua» (e il tocco) | il testo dell'esito; un'attesa automatica |
| `fine` | classifica dai punti, chi ha vinto | «ancora», «un'altra partita», «ricomincia» | il titolo della fine |

In tutte le fasi valgono anche le domande standard (§ 4) e, fuori dall'elenco del gioco, le forme
di Calliope di sempre: «chiudi il gioco», «basta», «esci». La fase `fine` è l'unica fase terminale;
ogni altra fase deve avere almeno un comando attivo o un'uscita a tempo, e lo controlla la prova
di fumo (§ 7).

**Fasi aggiunte dal gioco**: qualunque nome `[a-z][a-z0-9_]{0,23}`, con una pagina scelta tra i
modelli (§ 5), i suoi comandi e l'elenco `verso` delle fasi in cui può andare. Una mossa che porta
in una fase non dichiarata in `verso` è un errore del motore, e la prova di fumo lo dice con fase,
comando e valore.

### 2.2 I nomi dei giocatori (testo libero a voce: come)

Il nome detto a voce è testo libero: al riquadro oggi arriva **mai** testo libero dalla voce, ed è
una garanzia da non perdere. Strade valutate:

| Strada | Pro | Contro | Scelta |
|---|---|---|---|
| A. «Giocatore 1…N» subito | zero attrito, sempre | anonimo | **sì, predefinita** |
| B. «gioco anch'io» con la voce riconosciuta | forma chiusa; il nome viene da chi parla (`_giocatore_dalla_voce`: sopra soglia, margine, lunghezza), come `giocatore: true` di oggi | serve una frase abbastanza lunga; gli ospiti restano «Ospite N» | **sì** |
| C. nomi scritti sullo schermo (campo del motore) | qualunque nome, anche per ospiti e bambini | tastiera sul telefono; il nome poi lo dice Calliope | **sì**, con i controlli sotto |
| D. «il terzo si chiama Pippo» al modello, con un tool `gioco_nome(posto, nome)` | naturale | un turno del modello; testo libero che entra nel riquadro | **no** per ora (domanda 1) |
| E. elenco dei nomi di casa sui pulsanti | un tocco | i nomi di casa sullo schermo di stanza davanti agli ospiti | **no** |

Il nome scritto (C) resta nel riquadro, che non ha rete. Va però nell'istantanea, e Calliope lo
dice («Tocca a Pippo»): passa quindi dai controlli delle frasi dei giochi (`riferire.controlla_testo`,
il guardiano con un minore nella partita) e da una forma chiusa: lettere, spazi e apostrofo, al
più 20 caratteri, al più due parole. Un nome fermato si mostra sullo schermo e a voce diventa
«Giocatore 3». Una partita di prova (`"prova": true`) non fa dire nomi scritti.

### 2.3 Il formato: manifesto **e** logica, con compiti diversi

```json
"scheda": {
  "tipo": "gioco", "file": ["logica.js"], "stile": "tema.css",
  "giocatori": {"min": 1, "max": 4},
  "macchina": {
    "inizio": "turno",
    "fasi": {
      "turno": {"pagina": "scelte", "turni": true, "verso": ["esito"],
                "comandi": {
                  "porta": {"forme": ["porta {n}", "la porta {n}", "{n}"],
                            "n": {"da": 1, "a": 9}, "etichetta": "Porta {n}"}}},
      "esito": {"pagina": "messaggio", "verso": ["turno", "fine"]}
    }
  }
}
```

```js
const GIOCO = {
  nuovaPartita({ giocatori }) { return { porte: 3 + giocatori, aperte: [] }; },
  attivi: { turno: (d) => ({ porta: chiuse(d) }) },        // restringe, mai allarga
  mosse: { turno: { porta(d, { valore, chi }) {
    return { dati: {...}, punti: 1, esito: "Dietro la porta 3 c'è una zucca!",
             fase: "esito", dopo: finita ? "fine" : "turno" };
  } } },
  vista: { turno: (d) => ({ titolo: "Quale porta apri?" }) },
};
```

**Perché nel manifesto** fasi, comandi, forme e domini: il server li deve conoscere **senza
eseguire il codice del gioco** (riconosce la voce, valida l'istantanea); chi approva li sente
(«si gioca a voce, con 3 fasi e 2 comandi»); la revisione onesta può confrontare i requisiti con la
macchina dichiarata invece di leggere 60 000 caratteri di JavaScript; una versione nuova che
aggiunge un comando lo dice come un permesso nuovo (come oggi `ascolta`). **Perché in JS** le mosse
e i domini di adesso: sono regole del gioco (quali porte sono chiuse), cambiano a ogni mossa e il
server non esegue JavaScript.

Scartate:
- **Tutto nel manifesto** (mosse come tabelle di transizione): non esprime regole vere (punteggi,
  sorteggi, condizioni), e l'agente finirebbe a scrivere un linguaggio dentro il JSON.
- **Tutto in JS** (la macchina dichiarata a runtime, `motore.fasi({...})`): il server la saprebbe
  solo dopo aver aperto il riquadro, non la potrebbe validare all'approvazione né dire a chi
  approva, e la voce si fiderebbe di ciò che il riquadro dichiara.
- **Una libreria di stati generica** (XState o simili) nel riquadro: dipendenza in più, concetti
  in più per l'agente, e i pezzi che servono qui (turni, punti, classifica, nomi) non li dà.

### 2.4 Chi tiene lo stato

| Strada | Pro | Contro |
|---|---|---|
| **Riquadro (motore) scrittore unico, server con la copia** | la logica gira dove gira già (browser); latenza zero sui tocchi; il server valida e non esegue codice | il server si fida di ciò che il riquadro dice di sé (ma lo valida contro il manifesto) |
| Server autorevole | anti-imbroglio | eseguire il JS del gioco sul server (Node in un container a ogni mossa: 0,17–0,22 s misurati il 05/10, troppo per un gioco a tocchi) o riscrivere la logica in Python: no |
| Entrambi, con fusione | — | due fonti di verità, il rischio dell'analisi del flusso |

**Scelta: il motore nel riquadro è l'unico che scrive.** Dopo ogni mossa (o all'avvio, o a
«Riapri») manda il messaggio `stato` con l'**istantanea**:

```json
{"n": 7, "fase": "turno", "tocca": "Bianca", "turno": 1,
 "giocatori": [{"nome": "Ada", "punti": 3}, {"nome": "Bianca", "punti": 5}],
 "esito": null, "comandi": {"porta": [1, 3, 4], "ricomincia": true}}
```

Il server la **valida** contro il manifesto approvato e la tiene per il posto (`Posto.istantanea`,
al posto di `Posto.attivi`): `n` che cresce, fase dichiarata, comandi del manifesto per quella
fase, valori dentro il dominio dichiarato, nomi nella forma chiusa del § 2.2, punti interi
limitati, esito al più 160 caratteri. Una istantanea non valida si scarta (regola
`gioco_stato_non_valido`) e il gioco resta senza comandi a voce finché non ne manda una buona.

**Come non divergono.** (1) Turni, punti, fase e nomi sono campi del motore, non dell'agente: la
logica restituisce `dati` (suoi, opachi) e al più `punti`, `esito`, `fase`, `dopo`. (2) Il comando
a voce che il server manda porta `n`; il motore lo rifiuta se nel frattempo è cambiata
l'istantanea (un tocco arrivato prima), e lo dice al server (`rifiutato: vecchio`): il prototipo
lo fa («istantanea vecchia»). (3) Il server non deduce mai lo stato: i comandi attivi, la finestra
senza nome e le risposte di § 4 vengono solo dall'ultima istantanea valida. (4) Lo stesso codice
del motore gira nel riquadro e nella prova di fumo (un file solo, come oggi `RUNTIME_JS` e
`fumo_js.mjs` condividono l'interfaccia `calliope`).

**Ripresa.** Oggi «Riapri» o una pagina ricaricata fanno ripartire la partita. Il motore può
mandare anche i `dati` interi (opachi, ≤ 16 kB come `salva`) e il server glieli restituisce
all'avvio: la partita riprende dov'era. Non è un secondo scrittore (il server li conserva e non
li legge). Domanda 7.

**Partite condivise** tra schermi: oggi ogni riquadro applica le mosse che riceve. Con il motore il
primo posto sarebbe l'autorevole e gli altri riceverebbero istantanee e vista. È un passo a sé
(dopo il § 9), e la macchina nasce per uno schermo (domanda 6).

### 2.5 La via libera per eccezione: la «tela»

Per i giochi in tempo reale o senza turni (memory a tempo, un gioco d'abilità, un disegno): una
fase con `"pagina": "tela"` e `"tempo_reale": true`. Dentro la fase il gioco ha un'area del palco
tutta sua (`GIOCO.tela.avvia(area, dati, motore)`, DOM o canvas), riceve i tocchi e i comandi della
fase come eventi, e ne esce con `motore.passa("fine", {punti})`. Preparazione, fine, classifica,
istantanea e domande standard restano di Calliope. Una tela ha sempre il comando standard «fine
partita» (un'uscita garantita: «basta» resta di Calliope). Chi approva sente «è un gioco in tempo
reale». Un gioco tutto libero è `preparazione → tela → fine`: è la via d'uscita per ciò che non
sta nei turni, senza un secondo modo di scrivere i giochi. Le fasi `turni: false` coprono i
giochi senza turni ma a mosse (chiunque muove, con il nome riconosciuto dalla voce se c'è).

## 3. Comandi a voce per fase

### 3.1 Forme con uno slot

Un comando ha forme intere come oggi, e al più **uno slot** `{n}` per forma, di due tipi:
- **numero**: `"n": {"da": 1, "a": 9}`, al più 100 valori (i numeri in parole di `gioco_voce`
  arrivano a 100);
- **voce di un elenco chiuso**: `"colore": {"valori": ["rosso", "blu", "verde"]}`, al più 24
  valori, ognuno di 1–2 parole.

**Lo slot è un'abbreviazione di un elenco.** A ogni istantanea il server espande le forme sul
dominio **di adesso** (quello del manifesto, ristretto da `attivi` nel riquadro): «porta {n}» con
le porte 1, 3, 4, 5 chiuse sono le forme intere «porta 1», «porta 3», «porta 4», «porta 5». Il
confronto resta `normalizza` + ricerca per intero in un dizionario, come oggi. Il principio 10 vale
alla lettera: un insieme finito e noto di frasi brevi, riconosciute per intero, con un effetto
reversibile (una mossa).

Validazione (`valida_elenco`, estesa): lo slot conta come una parola; le forme espanse sul
dominio **dichiarato** non devono superare 5 parole e 40 caratteri, né coincidere con un'altra
forma della stessa fase (doppione: il prototipo lo trova, «2» vale per due comandi), né con le
forme riservate (uscita, stop) né con le forme standard della fase (§ 2.1). Lo **slot da solo**
(«{n}») si può solo con un dominio di al più 12 valori: «tre» per la porta tre è la cosa più
naturale da dire, e con 12 valori è lo stesso elenco chiuso che oggi si scrive a mano («uno»,
«due», «tre»). Tetto dell'espansione: 400 forme per fase.

Prototipo (`slot.py` sopra `gioco_voce.normalizza`, dominio 1, 3, 4, 5):

| Frase | Risultato |
|---|---|
| «la porta tre», «Calliope, porta 4!», «cinque», «apri la uno», «Ricomincia.» | porta 3, porta 4, porta 5, porta 1, ricomincia |
| «la porta due» (già aperta), «porta 37», «chiudi la porta», «porta», «la porta tre per favore», «tre gatti», «apri la porta tre» (forma non dichiarata), «porta la tre», «ventitré», «porta tre e quattro» | nessun comando |

15/15; espansione di 401 forme e confronto in 0,83 ms. In produzione l'espansione si fa una volta
per istantanea, non per frase.

### 3.2 Il valore fino al riquadro

Server → pagina: l'evento SSE «gioco» di tipo «comando» porta `{comando, valore?, giocatore?,
n}`. La pagina (schermo.js, anche sul telefono) accetta `valore` solo se è un intero 0–100 o una
stringa `^[a-z0-9][a-z0-9_]{0,23}$` (gli id dei valori di un elenco, scritti nel manifesto in forma
id: `"valori": {"rosso": ["rosso"], "blu": ["blu", "azzurro"]}`) e `n` intero; nient'altro. Il
motore ricontrolla il valore contro il dominio di adesso e risponde `stato` (mossa fatta) o
`rifiutato`. Tre controlli, come per il nome del comando oggi.

### 3.3 Finestra senza nome

Invariata nella forma: finché l'istantanea ha comandi attivi l'ascolto resta aperto per
`giochi_ascolto_s` dall'ultima mossa; senza nome valgono **solo** le forme espanse della fase e le
domande standard (§ 4); il resto si ignora (`gioco_finestra_ignorata`). Cambia la fonte: i comandi
attivi vengono dall'istantanea (`Giochi.ascolto`), non da `comandiAttivi`. In `esito` e `fine` la
finestra resta aperta (ci sono «avanti» e «ancora»); in una tela anche, con i soli comandi
dichiarati e «fine partita».

### 3.4 Ogni comando è anche un pulsante

Il motore disegna i comandi della fase nel modello di pagina: «scelte» fa un pulsante per comando
e per valore («Porta 1», «Porta 3»… dall'`etichetta`, o dalla prima forma con lo slot riempito),
«griglia» li mette nelle caselle che la vista assegna (`{casella: [riga, colonna], comando,
valore}`). Il tocco segue la **stessa strada** della voce: `motore.mossa(comando, valore)`, stessi
controlli, stessa istantanea. Una dichiarazione sola; un comando mai attivo o mai disegnato lo
trova la prova di fumo.

### 3.5 La via di mezzo: il giudice di fase

Quando la frase non è una forma della fase (dopo il nome, o nella finestra di sempre):

| Strada | Latenza | Costo | Errore possibile |
|---|---|---|---|
| Oggi: il modello della voce con `gioco_comando` e una riga di contesto | un turno intero (prima frase 1,18–1,42 s sulla DGX) | ~106 token di schema in ogni prompt della voce | sceglie un altro tool, o risponde a parole |
| **Giudice di fase**: chiamata separata, uscita vincolata da uno schema JSON (`enum` delle forme espanse + «nessuno») | **357 ms** mediana, p90 386 ms (portatile, e4b, misurato) | ~220 token di prompt, fuori dalla conversazione | solo un comando sbagliato tra quelli validi, o «nessuno» |
| Classificatore senza modello (somiglianza di parole) | ~1 ms | nessuno | decide il significato con una regola sul testo: contro il principio 10 |

**Scelta: il giudice di fase**, con l'uscita vincolata (Ollama `format` con lo schema; vLLM con i
suoi output strutturati): non può inventare un comando né un valore fuori dominio. È il «giudice
isolato» della macchina a stati del dialogo (§ 3.1 di
[`2026-10-10-macchina-stati.md`](2026-10-10-macchina-stati.md)) applicato al gioco: vede solo la
fase, i comandi e la frase, non la conversazione. Se dice «nessuno» la frase va al modello della
voce come oggi (con l'istantanea nei dati del turno, § 4). Una mossa capita dal giudice si dice
con l'etichetta («Porta tre.»): è un'interpretazione delle parole, e chi parla deve sentire cosa
ha capito (domanda 5). Il tool `gioco_comando` resta solo con il giudice spento.

**Misura** (prototipo `giudice.py`, portatile RTX 5070 Laptop 8 GB, `gemma4:e4b-it-qat` su Ollama,
`think: false`, temperatura 0, `num_ctx` 8192, 22 frasi × 2 giri a caldo; il gioco delle porte con
la 2 già aperta):

| Prompt | Giuste | Mosse al posto di «nessuno» | Mediana | p90 |
|---|---|---|---|---|
| A: descrizione + «nel dubbio, nessuno», «nessuno» in fondo all'elenco | 12/22 (sempre «nessuno») | 0/12 | 345 ms | 399 ms |
| B: comandi con il loro significato, «nessuno» in testa, cinque esempi, «vale l'ultima scelta» | **21/22** | 1/12 | **357 ms** | 386 ms |

Giuste con B: «apri la terza», «voglio la porta numero quattro», «proviamo con la prima», «apriamo
l'ultima», «uno, no aspetta, la cinque», «ricominciamo da capo»; e «nessuno» per «la porta due»
(già aperta), «apri la sei», «chiudi la porta che c'è corrente», «mamma, hai visto le chiavi?»,
«a chi tocca?». L'errore: «apri la tre e poi la quattro» → porta 4 (la regola «vale l'ultima»
batte «più mosse insieme»). È reversibile (una mossa), ma dice che il prompt del giudice va
scritto da Calliope, misurato e tenuto nelle prove col modello, mai lasciato all'agente.

**La cache del prompt della voce** (prototipo `cache.py`, stesso modello e stesso `num_ctx`):
voce con 4 901 token di sistema → giudice → voce: il prefill della voce dopo il giudice resta
78–90 ms (prima 93–107), quindi Ollama tiene la cache della voce e il giudice non la rovina. Con
un `num_ctx` diverso Ollama ricaricherebbe il modello (trappola nota): il giudice usa quello della
voce.

**Sulla DGX** il giudice va sul rilevatore e4b già residente (piano della macchina: «rilevatore
e4b separato»), stima 0,2–0,35 s; senza rilevatore separato sul modello della voce. **Senza il
nome** nella finestra del gioco il giudice resta **spento** all'inizio
(`giochi_giudice_senza_nome: false`): ogni frase della stanza diventerebbe una chiamata al modello,
e una chiacchiera («dai, apri la tre!» detto a un altro) una mossa. Prima si misura quante frasi la
finestra ignora oggi (`gioco_finestra_ignorata` in `calliope stato --turni`), poi si decide
(domanda 2).

## 4. Calliope sa a che punto è il gioco

Senza che l'agente lo programmi, perché turno, punti, fase e nomi sono del motore:

- **Domande standard** (forme chiuse di ogni fase, anche nella finestra senza nome; regola
  `gioco_stato_detto`): «a chi tocca?» → «Tocca a Bianca.»; «quanti punti ho?» → i punti di chi
  parla se la voce è riconosciuta in quella frase, altrimenti quelli di tutti; «chi vince?», «come
  siamo messi?» → la classifica in una frase. Le frasi le compone il codice dall'istantanea:
  nessun modello, testo→voce ~0,35 s. Contrari in `prova_testo`: dentro una frase più lunga («a chi
  tocca adesso secondo te, la porta?») va al giudice o al modello; senza gioco aperto sullo
  schermo del satellite non vale; con una domanda di Calliope in sospeso va al modello.
- **Le altre domande** («chi sta perdendo?», «quante porte restano?»): al modello della voce con
  l'istantanea nei dati del turno (`t.contesto_gioco`, oggi la riga dei comandi): «Sullo schermo il
  gioco «Apri le porte», fase turno: tocca a Bianca. Punti: Ada 3, Bianca 5. Comandi: porta 1, 3,
  4; ricomincia.» Circa 60 token (stima: 210 caratteri / 3,47). Il testo dell'esito della mossa è
  del gioco e **non** va al modello né si dice: è un dato non fidato (si mostra sullo schermo).
  Per farlo dire c'è `di`, con i suoi controlli.
- **In futuro** la partita diventa un'attività della macchina a stati del dialogo
  (`attivita: gioco:<partita>`), con un profilo dei tool ridotto mentre si gioca (§ 3.11 di
  [`2026-10-10-macchina-stati.md`](2026-10-10-macchina-stati.md)). Non serve per i passi qui sotto.

## 5. Pagine a palco fisso

### 5.1 Il palco

Il motore disegna dentro un `#palco` di misura fissa, scalato con `transform: scale(s)` e
centrato, `s = min(larghezza / W, altezza / H)`, con `overflow: hidden` sul riquadro: mai scroll.
Due palchi:

| | Palco | Su un telefono 390×844 in verticale | Su una TV 1920×1080 |
|---|---|---|---|
| Orizzontale | 1280×720 | scala 0,30: un pulsante da 56 px diventa 17 px, la fascia da 36 px 11 px (troppo piccoli) | scala 1,5 |
| **Verticale** | **720×1280** | scala 0,59 (misurata nel prototipo a 504×749 di finestra utile): 56 px → 33 px | — |

**Scelta**: i modelli di pagina di Calliope hanno **entrambe** le impaginazioni e il motore sceglie
dal rapporto della finestra; una tela può dichiarare un orientamento solo
(`"orientamento": "orizzontale"`) e allora il telefono in verticale mostra «Gira il telefono»
(domanda 3). Scartato un palco solo con le bande nere: sul telefono in verticale i testi
diventano illeggibili (tabella).

### 5.2 I modelli di pagina

| Modello | Contenuto (dalla `vista` della logica e dall'istantanea) |
|---|---|
| `titolo` | titolo grande, sottotitolo, un pulsante («Inizia») |
| `scelte` | titolo, una griglia di pulsanti (uno per comando e valore), fascia dei punti |
| `griglia` | una scacchiera R×C (al più 12×12) di caselle con testo, disegno (`risorsa`) o colore; le caselle che sono comandi sono pulsanti |
| `messaggio` | un testo grande (l'esito), i punti guadagnati, «Avanti» |
| `punteggi` | la tabella dei giocatori con i punti e chi tocca |
| `classifica` | podio e «Ancora» (la fine) |
| `tela` | un'area libera del palco per l'eccezione (§ 2.5) |

La preparazione e la fine usano `titolo`, `scelte` e `classifica` già scritti. La vista di una fase
restituisce **dati**, mai DOM: `{titolo, sottotitolo, caselle, testo}`. Il disegno è di Calliope.

### 5.3 Il tema, ridisegnabile senza toccare la logica

`tema.css` contiene solo variabili (`--sfondo`, `--testo`, `--primario`, `--accento`,
`--carattere`, `--raggio`, `--ombra`) e decorazioni per classe dei modelli (`.pulsante`,
`.casella`, `.titolo`), più i disegni SVG in `risorse`. «Fai le porte più spaventose» cambia
`tema.css` e le risorse, non `logica.js`: la prova di fumo della logica non si rifà, solo quella
del palco. Il motore mette i suoi valori predefiniti prima del tema (lo sfondo chiaro di oggi,
`_STILE_BASE`, resta il predefinito). Il CSS del tema non può spostare i contenitori dei modelli
(`position`, `width`, `height`, `transform` delle classi del motore si ignorano: il motore li
mette in linea con `!important`).

### 5.4 Come si verifica che niente esca dal palco

Cosa c'è già: `prove/cdp.py` comanda Edge o Chromium senza finestra con il protocollo DevTools (le
prove `*_pagina` sul portatile Windows); sulla DGX **non c'è un browser** (il 05/10: «Edge senza
finestra non c'è sulla DGX; Node in un container sì»), e la prova di fumo gira in Node con un DOM
finto senza impaginazione (le misure valgono sempre 100×100). Tre difese, in quest'ordine:

1. **Per costruzione**: modelli con aree fisse, testo che si adatta (si rimpicciolisce a passi di
   2 px fino a un minimo), griglie che dividono lo spazio. Un gioco che usa solo i modelli non ha
   modo di uscire dal palco, se non con un testo lunghissimo.
2. **Misura nel motore, sempre**: dopo ogni disegno il motore controlla gli elementi del palco
   (`getBoundingClientRect` fuori dai bordi; `scrollWidth`/`scrollHeight` oltre il riquadro =
   testo tagliato) e manda `palco` con al più tre elementi descritti (tag, classe, 30 caratteri).
   Nella partita di prova `palco` è ammesso (come `comandi` oggi: un ingresso di diagnosi, niente
   dati di Calliope) e arriva al collaudo: «Sullo schermo il titolo dell'esito è tagliato.». È la
   verità sul dispositivo vero, ma solo per le pagine viste.
3. **Prova del palco al collaudo, nel browser vero senza finestra**: il documento del riquadro con
   l'interfaccia `calliope` finta, le strade dell'esploratore (§ 7) che visitano ogni fase, a
   1280×720, 1920×1080, 390×844 e 844×390 (`Emulation.setDeviceMetricsOverride` di DevTools: le
   finestre di `--window-size` in modalità senza finestra non sono esatte, nel prototipo 390×844
   è diventata 504×749). Sul portatile con Edge c'è già tutto; sulla DGX serve un'immagine con
   Chromium per arm64 nella sandbox (stima: +300–400 MB, da verificare; la regola delle
   dipendenze native vale per Calliope, non per un container della DGX). Domanda 4.

Prototipo (`palco.html`, Edge 154 senza finestra, `--dump-dom`): la pagina «scelte» con 6 porte e
la fascia dei punti non ha difetti a nessuna misura; la pagina con un titolo di 130 caratteri e un
elemento messo apposta a x=1200 dà `testo tagliato: <div class="titolo">` e `fuori dal palco: <div
class="difetto">` a tutte e quattro le misure, in 0,8–1,1 s per misura (processo nuovo ogni volta).

## 6. Cosa scrive l'agente

| File | Cosa | Chi lo prova |
|---|---|---|
| manifesto (`scheda.macchina`) | fasi, comandi, forme, domini, pagine, `verso` | `scheda.normalizza` all'approvazione e alla consegna |
| `logica.js` | `GIOCO`: `nuovaPartita`, `mosse`, `attivi`, `vista` (dati, non DOM), facoltativa `tela` | i test dell'agente (node:test) e la prova di fumo per fasi |
| `logica.test.js` | test delle regole | Node nel container |
| `tema.css`, `risorse` | aspetto | la prova del palco |

Niente più `gioco.js` obbligatorio: il disegno è del motore (una tela lo scrive in `logica.js` o in
un `tela.js`). Spariscono le cause del caso dell'11/10: costanti doppie tra due file (un file solo),
eccezioni dei gestori (i gestori sono del motore, che cattura ogni eccezione della logica e la
mostra), la preparazione con i nomi vuoti (è di Calliope).

**Lo scheletro nuovo** (`scheletri.GIOCO`): il manifesto con due fasi, `GIOCO` delle porte, un
test, e una riga «Preparazione, turni, punti, esito, classifica e «ancora» sono di Calliope: non
scriverli. Ogni comando è anche un pulsante.» Circa **540 token** (1 875 caratteri / 3,47; oggi
2 281 caratteri, ~657). Il contratto § 5 si riscrive: via `comandiAttivi`, `quandoComando`,
`sicuro()` e il DOM; dentro la macchina, i modelli di pagina, gli slot, la tela. Stima ~1 000
token (oggi ~1 086), da rimisurare con il tokenizer di Qwen3.6 sulla DGX.
`requisiti.CAPACITA_GIOCO` dice cosa si può dichiarare («comandi a voce brevi per fase, anche con
un numero o una scelta di un elenco») e cosa no («frasi libere dentro il gioco»).

## 7. La prova di fumo per fasi

Si aggiunge a quella di oggi (`fumo_js.mjs`), con lo stesso motore del riquadro:

1. **Visita in ampiezza** degli stati: da `preparazione` con ogni numero di giocatori, ogni
   comando attivo con **ogni valore** del dominio; stato = fase, turno, punti, dati (deduplicati).
   Tetto 5 000 stati.
2. **Errori** che dice con fase, comando, valore, file:riga e la strada (gli ultimi 4 passi):
   eccezione di una mossa; risultato senza `dati`; fase fuori da `verso`; **fase senza uscita**
   (nessun comando attivo, non `fine`, senza uscita a tempo); fase dichiarata **mai raggiunta**;
   comando dichiarato **mai attivo**; dominio di `attivi` fuori da quello dichiarato; `vista` che
   lancia o restituisce campi sconosciuti.
3. **Partite intere**: 20 partite a caso (seme fisso, ripetibili) fino a `fine` entro 500 passi;
   una che non finisce è un errore («non arriva alla fine in 500 passi, ferma in «bonus»»).
4. **Tela**: tocchi a caso e tempo che scorre come oggi, più «fine partita»; deve uscire entro il
   tempo dichiarato (`durata_max_s`, al più 10 minuti simulati).

Prototipo (`esplora.js` + `motore.js` + `porte.js`): il gioco delle porte giusto, 5 000 stati in
78 ms, tutte le fasi raggiunte, 20 partite intere in 9–16 passi; la variante con la fase «bonus»
senza uscita, in 52 ms: «fase «bonus» senza uscita: nessun comando attivo (strada: inizia → porta
2)», «fase «fine» dichiarata ma mai raggiunta», «comando «bonus.prendi» mai attivo», «partita 1:
non arriva alla fine in 500 passi». Nel prototipo il turno passa al giocatore dopo già durante
l'esito (l'istantanea dice «tocca a Giocatore 2» mentre mostra la mossa del primo): nel motore vero
il turno passa all'uscita da `esito`.

La revisione onesta (`requisiti`) guadagna un pezzo: «porte in numero variabile» e «scelta della
porta a voce» si leggono nella macchina dichiarata (`porta {n}` con `n` da 1 a 9, `attivi` che
restringe) prima che nel codice.

## 8. Sicurezza

- **Il riquadro non cambia**: `<iframe sandbox="allow-scripts">` senza `allow-same-origin`, la CSP
  del documento (`connect-src 'none'`, script con l'impronta), il runtime che toglie rete, WebRTC e
  worker, il cane da guardia. Il motore è codice di Calliope **dentro** un contesto non fidato:
  gira nello stesso spazio globale del gioco, che potrebbe cambiarne il comportamento (il motore
  si chiude in una funzione e congela ciò che espone, ma non è un confine). Il confine resta
  dov'è oggi: tutto ciò che esce dal riquadro lo ricontrollano la pagina e il server.
- **Cosa esce dal riquadro**: `stato` (l'istantanea, validata contro il manifesto, § 2.4),
  `rifiutato`, `palco` (diagnosi), e i tipi di oggi. **Cosa entra**: il comando con al più un
  valore (intero 0–100 o un id di `[a-z0-9_]`), il nome di chi gioca come oggi, `n`; mai audio né
  testo libero.
- **`TIPI_PROVA`** diventa `pronto`, `battito`, `fine`, `errore`, `guasto`, `stato`, `rifiutato`,
  `palco`, `chiuso`: l'istantanea e la diagnosi sono ingressi per la voce e per il collaudo, non un
  ponte verso Calliope. In prova Calliope non dice nomi scritti né testi del gioco; `salva`,
  `leggi`, `manda`, `chat`, `di` e `azione` restano vietati.
- **Cosa può fare un comando**: una mossa nel gioco aperto sullo schermo di quel satellite. Nessun
  tool, nessun permesso, reversibile. Le forme che coprono uscita e stop non si dichiarano;
  «chiudi il gioco», «basta», «esci» restano di Calliope anche in una tela.
- **Il gioco non allarga ciò che sente**: forme e domini dichiarati sono un tetto; `attivi`
  restringe soltanto; l'istantanea che dichiara un valore fuori dal manifesto si scarta.
- **Testo che Calliope dice**: solo i campi del motore (nomi, punti, chi tocca) con la forma chiusa
  del § 2.2 e i controlli di `di`; l'esito della mossa no.
- Il giudice di fase vede la frase e l'elenco dei comandi, non la conversazione né dati di casa;
  l'uscita vincolata non ha campi liberi.

## 9. Profilo ridotto da 8 GB

| Funzione | Sulla DGX | Nel profilo da 8 GB (portatile, gemma4 e4b, Whisper sulla GPU) |
|---|---|---|
| Motore, fasi, pagine, palco, pulsanti | nel browser degli schermi | uguale: 0 VRAM |
| Forme chiuse con slot, domande standard | Whisper + confronto (< 1 ms) | uguale: 0 VRAM in più |
| Finestra senza nome | Whisper su ogni frase della stanza per 60 s | uguale; Whisper divide la GPU con la voce: `giochi_ascolto_s` si può abbassare |
| Giudice di fase | rilevatore e4b residente, stima 0,2–0,35 s | sul modello della voce già in memoria: **357 ms misurati**, nessuna VRAM in più, cache della voce intatta; `giochi_giudice: false` lo spegne (si torna a `gioco_comando`) |
| Istantanea nei dati del turno | ~60 token | ~60 token su una finestra più piccola: si accorcia ai soli comandi oltre una soglia della finestra |
| Agente che scrive il gioco, prova di fumo per fasi | qwen3.6 su vLLM, Node nel container | **non c'è**: il piano della macchina mette l'agente «da configurare» (o su un altro computer) e su Windows il codice dell'agente non si esegue. Un gioco scritto altrove si usa uguale |
| Prova del palco nel browser | Chromium nel container (da costruire) | Edge c'è (`prove/cdp.py`), ma serve solo dove gira l'agente |

## 10. Piano a passi piccoli

Niente compatibilità: i giochi già approvati con `ascolta` piatto e `gioco.js` libero smettono di
aprirsi al passo 4 (si rifanno con lo sviluppo; domanda 9).

| Passo | Cosa | Prove | Stima |
|---|---|---|---|
| 1 | **Slot nei comandi** (oggi piatti): forme `{n}` con dominio numerico o elenco in `gioco_voce` (validazione, espansione sul dominio, doppioni), `comandiAttivi` che restringe anche i valori, `valore` fino al riquadro (server, schermo.js, runtime) | `prova_testo` (le 15 frasi del prototipo e i doppioni), `prova_gioco_voce`, `prova_giochi_pagina` (valore nel riquadro, valori non validi scartati dalla pagina) | 0,5 g |
| 2 | **Motore senza DOM** (`calliope/estensioni/motore_gioco.js`): fasi standard, turni, punti, istantanea con `n`; `scheda.macchina` validata in Python; messaggio `stato` al posto di `comandi`, `Posto.istantanea`, comandi con `n`; `ascolto` dall'istantanea | `prova_gioco_macchina` nuova (a secco: validazione, istantanee cattive scartate, comando vecchio rifiutato, banco d'attacco dell'istantanea), `prova_giochi`, `prova_gioco_voce` | 1,5 g |
| 3 | **Prova di fumo per fasi** (esploratore in `fumo_js.mjs` con lo stesso motore) | casi in `prova_gioco_voce`/`prova_agente_guida`: gioco buono, fase senza uscita, fase mai raggiunta, comando mai attivo, mossa che lancia con file:riga, partita che non finisce | 1 g |
| 4 | **Palco e pagine**: palco 1280×720 e 720×1280, i sei modelli più la tela, preparazione (numero, «gioco anch'io», nomi scritti) e fine standard, tema a variabili, testo che si adatta, misura `palco`; via `ascolta` piatto, `quandoComando`, `comandiAttivi`, `gioco.js` obbligatorio | `prova_giochi_pagina` e `prova_telefono_schermo` con un gioco nuovo (`prove/giochi/porte` rifatto) alle quattro misure: ogni modello visitato, zero difetti di palco, un difetto messo apposta trovato; pulsanti = comandi | 2 g |
| 5 | **Calliope sa il gioco**: domande standard (regola `gioco_stato_detto`), istantanea nei dati del turno, nomi detti con i controlli | `prova_testo` (forme e contrari), `prova_gioco_voce` (chi parla, ospite, minore col guardiano) | 0,5 g |
| 6 | **Giudice di fase** (`giochi_giudice`, `giochi_giudice_senza_nome: false`), prompt di Calliope, `gioco_comando` solo come ripiego | a secco con il modello finto; con il modello (`prova_gioco_giudice_ollama`, le 22 frasi del prototipo e altre: ≥ 20/22, nessuna mossa su una domanda); misura sulla DGX con `calliope stato --turni` | 1 g |
| 7 | **Agente**: scheletro e contratto § 5 nuovi, `CAPACITA_GIOCO`, la revisione legge la macchina dichiarata | `prova_agente_guida` (lo scheletro passa test, fumo per fasi e consegna), `prova_contesto_agenti` (token), poi il giro vero sulla DGX: il gioco di Halloween a voce con «la porta tre», «apri la terza», «a chi tocca?» | 1 g + giro |
| 8 | **Prova del palco al collaudo** nel browser vero: Chromium arm64 nella sandbox della DGX (se deciso), le strade dell'esploratore alle quattro misure | prova a secco con Edge sul portatile; immagine costruita e misurata sulla DGX (tempo, memoria) | 1–1,5 g |

Totale circa **9 giorni** più il giro vero. Dopo: partite condivise con il motore (il primo posto
autorevole), la partita come attività della macchina a stati del dialogo.

## 11. Domande aperte per chi amministra

1. **Nomi dei giocatori**: va bene «Giocatore N» subito, «gioco anch'io» con la voce e i nomi
   scritti sullo schermo? Un nome scritto lo dice anche Calliope (con i controlli) o resta solo
   sullo schermo? Il nome detto a voce al modello («il terzo si chiama Pippo») lo vuoi?
2. **Giudice senza nome** nella finestra del gioco: spento all'inizio, da decidere dopo aver
   misurato le frasi ignorate?
3. **Telefono in verticale**: i modelli di Calliope in entrambi gli orientamenti; una tela può
   dichiararne uno solo e far dire «Gira il telefono»?
4. **Chromium nella sandbox della DGX** per la prova del palco (immagine più grande, da misurare),
   o bastano la costruzione e la misura sul dispositivo al collaudo?
5. Dopo una mossa capita dal **giudice**, Calliope dice l'etichetta («Porta tre.») come oggi con
   `gioco_comando`, o resta muta perché lo schermo la mostra?
6. **Partite condivise** tra schermi rimandate a dopo la macchina per uno schermo?
7. **Ripresa** della partita dopo «Riapri» o una pagina ricaricata (lo stato salvato dal server,
   ≤ 16 kB)?
8. **Esito**: «avanti» a voce o al tocco, oppure anche da solo dopo qualche secondo (e quanti)?
9. **I giochi già approvati**: si tolgono al passo 4 o restano chiedibili (senza voce né palco)
   finché non li si rifà?

## Aggiornamento del 13/10: cosa è fatto

Fatto sul ramo `giochi-stati` (dettagli in [giochi](../aree/giochi.md), «La macchina a stati di
Calliope», e in [agenti-estensioni](../aree/agenti-estensioni.md)): del passo 1 lo slot come
abbreviazione di un elenco, espanso **una volta all'approvazione** sul dominio dichiarato nei
comandi a voce piatti (`porta_3`) e ristretto a runtime dal motore con `comandiAttivi`, invece
che a ogni istantanea dal server (il server e la regola `gioco_comando` restano quelli
dell'11/10); del passo 2 il motore, `scheda.macchina` validata e l'istantanea nel motore (non
ancora mandata al server né numerata); il passo 3 (la prova di fumo per fasi); del passo 4 la
tela e un disegno semplice per `scelte` e `messaggio` (non il palco fisso né i sei modelli); il
passo 7 (scheletro, contratto, `CAPACITA_GIOCO`) e, in più, gli esempi di accettazione dei
giochi (domanda 5 della ricerca sul flusso a fasi). Restano i passi 4 (palco, giochi vecchi
tolti), 5, 6 e 8, il resto del 2 lato server e le scelte 1 (nomi), 7 (ripresa) e 6 (partite
condivise) delle risposte del 12/10.

## Aggiornamento del 14/10: il palco

Fatto sul ramo `giochi-palco` il passo 4 (dettagli in [giochi](../aree/giochi.md), «Il palco fisso»):
il palco 1280×720 e 720×1280 scalato alla finestra, i sei modelli di pagina più la tela,
l'impaginazione come funzione pura del motore (la stessa nel riquadro e in Node) che la prova di
fumo misura per ogni pagina raggiunta nei due orientamenti, la misura vera nel browser (tipo
«palco» a Calliope), i giochi vecchi tolti (decisione 9), scheletro e contratto aggiornati.
Rispetto al § 5.4: la difesa 2 (la misura nel motore) c'è; la 3 (il browser nella sandbox) non
serve per la misura del calcolo, che gira in Node, e resta scartata (decisione 4: così anche il
passo 8). Restano i passi 2 (lato server), 5 e 6 e le scelte 1, 6 e 7.

## Aggiornamento del 14/10 sera: il progetto finito

Fatto sul ramo `giochi-passi-finali` (dettagli in [giochi](../aree/giochi.md), «Lo stato della
partita»), con le risposte di chi amministra del 12/10:
- **Passo 2, lato server**: il motore manda dopo ogni disegno l'istantanea numerata (`stato` al
  posto di `comandi`), il server la valida contro il manifesto (`macchina.valida_istantanea`) e
  la tiene come stato della partita; i comandi a voce vengono solo da lì e portano il numero; il
  motore rifiuta quelli vecchi (`rifiutato`). Rispetto al § 2.4: `tocca` è la posizione e i
  comandi sono i nomi piatti (`porta_3`), non il dizionario `{porta: [1, 3, 4]}`; la stessa
  istantanea rimandata (un ridisegno) passa, perché `n` non deve calare, non per forza crescere.
- **Passo 5**: le domande standard (regola `gioco_stato_detto`, `calliope/gioco_stato.py`) e
  l'istantanea nei dati del turno, in busta (fonte `gioco`) con un nome scritto.
- **Passo 6**: il giudice di fase (`calliope/gioco_giudice.py`), con il prompt B scritto dal
  codice dai comandi della macchina; misura sul portatile con gemma4 e4b sulle 22 frasi del
  prototipo: 21/22 in due giri, mediana 313–323 ms (il prototipo: 21/22, 357 ms). Spento senza il
  nome (decisione 2); `gioco_comando` solo con il giudice spento.
- **Decisione 1**: «gioco anch'io» (comando standard `anchio`) con il nome dalla voce, «anch'io,
  sono Pippo» per chi non è riconosciuto, i nomi scritti toccando la fascia dei punti; Calliope
  dice i nomi scritti solo dopo i controlli (strada C del § 2.2; la D, il nome al modello, no).
- **Decisione 7**: la ripresa dopo «Riapri» dall'ultima istantanea valida (lo stato intero, al
  più 16 kB, opaco per il server).
- **Decisione 6** (rimandata, fatta qui perché la strada del § 2.4 era realizzabile così com'è):
  in una partita condivisa con la macchina e senza tela il primo riquadro pronto tiene la
  partita, gli altri schermi sono specchi che disegnano il suo stato e gli mandano le mosse; se
  chi la tiene se ne va, passa a un altro schermo. Non decide chi è quale giocatore.
- Il caso «porte» del banco della temperatura era già nel formato nuovo (riscritto con il
  palco): `--secco` ok.

**Resta** (*storico dal 15/10: «Gira il telefono» e chi è quale giocatore sono fatti, vedi
sotto*): «Gira il telefono» (decisione 3), la diagnosi del palco a voce al collaudo, chi è quale
giocatore nelle partite condivise, il giudice senza il nome (decisione 2, dopo la misura sulla
DGX), la partita come attività della macchina a stati del dialogo; il passo 8 resta scartato
(decisione 4). Il giro vero sulla DGX con l'agente.

## Aggiornamento del 15/10: chi è quale giocatore, «Gira il telefono»

Fatto sul ramo `giochi-giocatori` (dettagli in [giochi](../aree/giochi.md), «Chi è quale
giocatore»). Rispetto al § 2.2 e al § 2.4: il nome resta quello di prima (voce riconosciuta, «gioco
anch'io, sono Pippo», scritto), ma «gioco anch'io» lega anche il giocatore allo **schermo** (il
numero del posto, messo dal server per le mosse che arrivano da un altro schermo) e alla **voce**
(un segno opaco per partita: il riquadro non riceve il nome se il manifesto non lo chiede). Il
motore resta il solo scrittore e decide chi muove in una fase a turni; il server fa lo stesso
controllo sull'istantanea per far dire a Calliope «Tocca ad Ada.». «Gioco anch'io» a partita
cominciata: solo a voce, subito con `GIOCO.entra`, altrimenti dalla prossima partita. Rispetto al §
5.1 (decisione 3): `"orientamento"` solo su una tela, il palco dichiarato sempre, la fascia «Gira il
telefono» sul telefono girato e la frase detta una volta, senza blocco. **Resta**: la diagnosi del
palco a voce al collaudo, il giudice senza il nome (decisione 2, dopo la misura), la partita come
attività della macchina a stati del dialogo, il giro vero sulla DGX.
