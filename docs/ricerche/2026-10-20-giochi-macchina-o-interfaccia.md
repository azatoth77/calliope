# Giochi: la macchina a stati o un'interfaccia più piccola? (20/10/2026)

*Analisi in sola lettura, parte 1 della issue #198. Nessuna modifica al codice. Fatta sul codice
di `main` a `b032cd41`. Fonti: [giochi](../aree/giochi.md) per intero, le voci dall'11/10 al 20/10
di [agenti-estensioni](../aree/agenti-estensioni.md), il progetto
[`2026-10-12-giochi-macchina-stati.md`](2026-10-12-giochi-macchina-stati.md), le ricerche
[`2026-10-12-flusso-agente-fasi.md`](2026-10-12-flusso-agente-fasi.md) e
[`2026-10-19-solidita-harness-sviluppo.md`](2026-10-19-solidita-harness-sviluppo.md), le issue
#174, #192 e #197. Ho letto il codice: `estensioni/macchina.py`, `estensioni/motore_gioco.js`
(il nucleo `crea` per intero, il resto per parti), `gioco_voce.py`, `gioco_stato.py`,
`gioco_giudice.py`, `schermi/giochi.py` (i tipi del riquadro), `schermi/pagina/schermo.js` (i tipi
che passa), `estensioni/scheda.py`, `estensioni/contratto.py`, `estensioni/prompt.py`,
`agenti/scheletri.py`, `agenti/fumo_js.mjs`, `agenti/accettazione.py` (la parte dei giochi),
`prove/giochi/tris` e il caso `tris2` di `prove/manuali/banco_temperatura.py`. I registri dei lavori
sono sulla DGX e non li ho riletti: le cause dei fallimenti vengono da ciò che è scritto nei
documenti e nelle issue.*

## In breve

**La domanda.** La macchina a stati dei giochi (13–15/10) è nata per semplificare il lavoro
dell'agente, prima dell'harness di oggi. Il 20/10 sera, con tutto l'harness installato, la
correzione delle porte fa 8/8, ma il tris per due da zero fa 0/3. Chi amministra ritiene
Qwen3.6-35B-A3B adatto a un tris, e chiede se il problema sia nell'harness o nelle specifiche.

**Cosa dicono il codice e i casi veri.**

1. **Le garanzie di Calliope non dipendono dalle fasi.** Comandi a voce, giudice, «a chi tocca?»,
   istantanea validata, partite condivise, ripresa, chi è quale giocatore e palco usano quattro
   cose:
   - un elenco chiuso di comandi nel manifesto;
   - un'istantanea numerata con giocatori, punti, a chi tocca e comandi attivi;
   - uno stato serializzabile e una vista pura in forma chiusa;
   - preparazione, fine e disegno tenuti da Calliope.

   Niente di questo ha bisogno che il gioco dichiari fasi, `verso`, `dopo`, la fase «esito» o
   `ancora` (§ 2).
2. **Quei concetti costano all'agente.** Circa un terzo del §2 del contratto del gioco
   (≈ 3 300–3 500 caratteri su 9 141, il 36–38 %) descrive soltanto la macchina: fasi,
   preparazione, le tre forme di una mossa, `g.stato()`. Ci sono anche tre incoerenze verificate
   nel codice:
   - `tocca` è un nome in `g.stato()` e una posizione nel contesto della mossa;
   - `turno`, nel contesto della mossa, è il numero del giro, non chi muove, e il contratto non lo
     dice;
   - in una fase senza turni, quando non si sa chi ha mosso, i punti numerici vanno in silenzio
     al Giocatore 1.

   Tre testi suggeriscono un esito a ogni mossa: il contratto, il prompt dell'analisi e il gioco
   della partenza (§ 3.1).
3. **Gli errori dei giochi dal 14/10.** Su 14 lavori di gioco falliti nei banchi e nei casi veri,
   un'interfaccia senza fasi ne toglierebbe **5–6**. In 4–5 la causa principale è un concetto
   della macchina (la preparazione, «avanti» ed «esito», `dopo`, l'esito a ogni mossa), più un
   probabile sull'interfaccia della mossa. Il resto ha altre cause:
   - 3 vengono dalla transizione dai giochi di prima, che non c'è più;
   - 2 dalla regressione dell'harness chiusa da #192;
   - 3 dalla logica del modello e dalla forma della vista, che resta anche in C;
   - 1 dalla causa non scritta.

   Dal 19/10 la correzione di un gioco che c'è già fa 14/16, e 8/8 dopo #192. La macchina regge
   quando il gioco ha già la forma giusta. Cede quando l'agente deve uscire dalla forma
   dell'esempio di partenza (§ 3.3).
4. **Quasi tutto ciò che nel 13/10 copriva solo la macchina oggi lo copre anche l'harness.** Le
   cause dell'11–12/10 erano il `require`, le costanti doppie, l'esito annidato, i gestori che
   lanciano e i giri a vuoto. Oggi c'è il disegno di Calliope da una vista chiusa, che è un pezzo
   della macchina ma non ha bisogno delle fasi. In più ci sono la prova di fumo, gli esempi in sola
   lettura, le porte oneste, gli strumenti onesti e la partenza verde. Restano della macchina sola
   il disegno, la preparazione e l'istantanea, e nessuno dei tre richiede le fasi (§ 4).

**Raccomandazione (§ 6).**
1. Chiudere #197, per non misurare un contratto sbagliato.
2. Fare il banco della parte 2 su tre casi a **10 ripetizioni** ciascuno, con le soglie scritte
   prima:
   - `tris2` di oggi;
   - `tris2-solo-logica`: la macchina di oggi, ma l'agente scrive solo `logica.test.js`. Separa
     l'API dei test dall'interfaccia;
   - `tris-nudo`: JavaScript semplice, il tetto del modello.
3. Il prototipo dell'**opzione C come facciata sopra la macchina** (quattro funzioni pure su uno
   stato del gioco, tradotte in una macchina a una fase, 2–3 giorni) **solo se la misura lo
   indica**: `tris-nudo` alto, mentre `tris2` e `tris2-solo-logica` restano bassi (§ 7).

## 1. Cosa la macchina risolveva (casi veri dell'11–13/10)

| Caso vero | Cosa è successo | Cosa ha fatto la macchina | Oggi lo copre anche |
|---|---|---|---|
| Halloween, 11/10 (45 minuti a vuoto) | costanti dichiarate due volte in logica.js e gioco.js; `require` in gioco.js | un file solo (logica.js), niente gioco.js | il controllo della consegna sul `require` (`prompt._controlla_gioco`); un file solo non è un concetto della macchina |
| Halloween, 11/10 | eccezione della logica uscita dal gestore di «Inizia» (i nomi vuoti della preparazione) | i gestori e la preparazione sono del motore, che cattura ogni eccezione | — (è il disegno di Calliope, non le fasi) |
| Halloween, 11/10 | gioco.js riscritto per intero nove volte | niente DOM da scrivere | `modifica_file`, la diagnosi con file:riga (11/10), gli strumenti onesti (#185: stato già visto, modifica inversa) |
| Le porte, 12/10 (sei versioni sbagliate) | logica.js restituiva l'esito annidato, gioco.js lo leggeva al primo livello: sempre «Nessun punto!», con i test di logica verdi | la forma del risultato controllata dal motore; il disegno è di Calliope | il test del disegno con `apriGioco` (12/10 sera, prima della macchina); gli esempi di accettazione in sola lettura |
| Le porte, 12/10 | correzioni senza riprodurre, file identici | — | la riproduzione (12/10 sera), le porte oneste (#180) |
| Il progetto del 12/10 (§ 1) | Calliope non sapeva fase, turno e punti; due modi di dare i comandi a voce (`comandiAttivi`, `quandoComando`); la pagina scorreva | istantanea, comandi per fase, palco fisso | — (sono garanzie per Calliope, § 2) |
| La ricerca del 12/10 (strada D, domanda 5) | con gioco.js libero i selettori dei test cambiano a ogni versione | pagine standard e pulsanti dal nome del comando: test stabili | — (anche questo è il disegno di Calliope) |

La macchina ha risolto due famiglie diverse:
- **Per costruzione, dal lato del disegno.** Un file solo, nessun DOM, una vista chiusa, i gestori
  e la preparazione del motore. Sono le cause vere dell'11–12/10.
- **Dal lato di Calliope.** Istantanea, voce per fase, palco.

Le **fasi dichiarate dal gioco** (`verso`, `dopo`, la fase «esito» che blocca, `ancora`) non
rispondevano a un caso vero dell'agente. Venivano dal progetto: un gioco «è fatto di fasi»,
richiesta di chi amministra del 12/10.

## 2. Cosa garantisce oggi a Calliope, e se serve la macchina

Per ogni garanzia: che cosa legge davvero il codice di oggi, e se basterebbe un'interfaccia più
piccola.

| Garanzia | Dove | Cosa usa davvero | Servono le fasi? |
|---|---|---|---|
| Comandi a voce dichiarati, regola `gioco_comando`, finestra senza nome, «chi approva sente» | `macchina.ascolta`, `gioco_voce`, `Ciclo._comando_gioco` | l'elenco chiuso dei comandi con forme, slot e dominio **nel manifesto** (il server lo sa senza eseguire il gioco, § 2.3 del progetto); a runtime il sottoinsieme attivo | **no**: le fasi servono solo a dire in quale fase un comando può valere |
| Giudice di fase | `gioco_giudice.py` | i comandi attivi adesso (enum), le loro forme, il titolo | **no** (si chiama «di fase», ma legge i comandi attivi) |
| «A chi tocca?», «quanti punti ho?», «chi sta vincendo?», «cosa posso dire?» | `gioco_stato.py` | dall'istantanea: giocatori e punti, `tocca`, preparazione e fine, «ha appena giocato» durante l'esito | **no**: bastano tre stati (preparazione, gioco, fine) |
| Istantanea validata, numero `n`, comando vecchio rifiutato | `macchina.valida_istantanea`, `_t_stato`, `perCalliope` | `n` e lo stato pubblico li tiene il motore; il server controlla forma, tetti e comandi tra quelli possibili «per fase» (`per_fase`) | **no**: senza fasi la validazione è «tra i comandi dichiarati», sempre un insieme chiuso |
| Partite condivise (autorevole e specchi) | `Partita.motore_condiviso`, `nucleo.riprendi` | uno stato serializzabile e una vista pura: lo specchio disegna lo stato che riceve | **no** |
| Ripresa dopo «Riapri» | `Posto.ripresa`, `nucleo.riprendi` | lo stesso stato serializzabile (≤ 16 000 caratteri) | **no** |
| Chi è quale giocatore, «Tocca ad Ada» | `chiMuove`, `macchina.chi_muove` | `tocca` e se la mossa è a turni (`turni` per fase) | **no**: «a turni sì o no» per gioco, o `tocca: null` |
| «Gioco anch'io», nomi scritti, chi entra a metà | il motore, nella preparazione; `GIOCO.entra` | la preparazione di Calliope prima della partita, i nomi passati a `nuovaPartita` | **no**: la preparazione è di Calliope, non serve che il gioco la veda come una sua fase |
| Palco fisso, sei modelli di pagina, misura «fuori dal palco» | `impagina`, `controllaPalco`, `pagina(S)` | una vista in forma chiusa (testi, caselle) e il modello di pagina; i pulsanti dai comandi attivi | **no**: il modello si può dichiarare una volta per gioco (o restituire con la vista) |
| Fine con la classifica e «ancora» | il motore | i punti e il segnale «finita». La fase «fine» cancella `S.esito` (`motore_gioco.js:790`): il testo del risultato («Ha vinto Ada») si vede solo nei secondi dell'esito che precede la fine, non sulla classifica | **no** |
| Esito che va avanti da solo dopo `esito_s`, «avanti» | il motore | una fase di Calliope che blocca le mosse | è un concetto della macchina, ed è quello di #197 |
| Prova di fumo per fasi | `fumo_js.esplora` | comandi attivi, mosse, stati deduplicati, fine entro 500 passi, ogni pagina misurata | **no**: «fase senza uscita» diventa «stato non finito senza comandi attivi»; «fase mai raggiunta» sparisce |
| Esempi di accettazione dei giochi | `accettazione.test_js` | giocatori, mosse, poi fase, tocca, punti, attivi e non attivi, testo | **no**: «fase» diventa «finita sì o no» |
| La forma dei risultati controllata (la classe del 12/10) | `controlla`, `vista` del motore | il disegno è di Calliope da una vista chiusa | **no**: lo stato è opaco, e la vista resta chiusa |
| Sicurezza: niente testo libero dalla voce nel riquadro, niente DOM dell'agente fuori dalla tela | runtime, pagina, server | come oggi | **no** |

**Conclusione del § 2.** Le garanzie poggiano su quattro ingredienti:
1. un elenco chiuso di comandi nel manifesto;
2. un'istantanea numerata con preparazione, gioco o fine, a chi tocca, giocatori e punti, comandi
   attivi;
3. uno stato serializzabile e una vista pura in forma chiusa;
4. preparazione, fine, disegno e numero dell'istantanea tenuti da Calliope.

Le fasi dichiarate dal gioco, `verso`, `dopo`, `ancora`, la fase «esito» e i dizionari per fase
(`attivi[fase]`, `vista[fase]`, `mosse[fase][comando]`) non servono a nessuna garanzia. Fanno
soltanto la forma in cui oggi l'agente li deve scrivere.

Cosa perderebbe davvero Calliope togliendo le fasi:
- **la validazione per fase** dei comandi dell'istantanea, che diventa «tra i comandi dichiarati»
  (il principio 10 resta vero: l'insieme è finito e approvato);
- **i turni e i punti coerenti per costruzione**, se lo stato passa al gioco (§ 5, opzione C);
- **pagina e turni diversi da una fase all'altra**: con una fase sola valgono per tutto il gioco.
  Non è una garanzia, ma è espressività che si perde (§ 5, C).

## 3. Cosa costa all'agente

### 3.1 I concetti

Per scrivere un gioco l'agente deve conoscere, oltre al JavaScript:

1. le fasi sue e quelle di Calliope (preparazione, esito, fine), che non si dichiarano ma si
   nominano;
2. `inizio`, `verso` e `turni` per fase;
3. sette modelli di pagina, le caselle della griglia (colori, risorse, `comando` e `valore`);
4. i comandi: forme, slot `{n}`, dominio, etichetta, forme riservate, domande di Calliope;
5. `attivi[fase]`, che restringe e non allarga;
6. `vista[fase]`, solo testi, più le caselle nella griglia;
7. `mosse[fase][comando](dati, { valore, chi, giocatori, turno })` →
   `{ dati, punti, esito, fase, dopo, ancora }`, in tre forme ammesse e con due vietate (esito
   insieme a fase, dopo senza esito), più `dopo` diverso da «esito»;
8. i punti come numero «a chi ha mosso» o come elenco, e `ancora`;
9. `esito_s` e «avanti», che vale solo nella fase «esito»;
10. la preparazione: «Inizia» con min = max, «N giocatori» con min < max, «gioco anch'io»;
11. i nomi in `nuovaPartita({ nomi })` e `ctx.giocatori`; `GIOCO.entra`; `giocatore: true`;
    `condivisa`;
12. la tela, cioè la via libera: `GIOCO.tela[fase]`, `tela.esci`, l'orientamento;
13. l'API dei test: `apriGioco({ seme, inizia, giocatori })`, `g.tocca`, `g.comando`, `g.avanza`,
    `g.testo`, `g.palco`, e `g.stato()` nella sua forma esatta;
14. `module.exports` in fondo e niente `require` in logica.js.

**Incoerenze dell'interfaccia** (verificate nel codice):
- **`tocca` ha due significati.** In `g.stato()` è il **nome** di chi muove («Giocatore 1»), nel
  contesto della mossa e nell'istantanea del server è la **posizione** (`contesto(S)`,
  `perCalliope`). Un errore vero dei banchi è vicino ma diverso: il 14/10 sera (porte L7)
  l'agente ha scritto `stato.punti["Giocatore 1"]`. È la forma di `g.stato()` (i punti stanno in
  `giocatori[i].punti`, non in una mappa per nome), non nome contro posizione: dice che un
  `g.stato()` centrato sui nomi invita a cercare per nome.
- **`turno` nel contesto della mossa è il numero del giro**, non chi muove. Con due giocatori
  vale 1, 1, 2, 2… (provato con il nucleo del motore), e il contratto lo elenca senza dirlo
  (`mosse[fase][comando](dati, { valore, chi, giocatori, turno })`). Un `giocatori[turno]`
  restituisce `undefined` dal secondo giro. È **un'ipotesi** per il `TypeError: Cannot read
  properties of undefined (reading 'punti') [in logica.js:62]` del 20/10 sera (tris2 L5, #197), da
  verificare sul lavoro della DGX.
- **Chi muove sta in due posti.** Il motore tiene `tocca`, ma un tris deve sapere quale segno
  mettere. Ha tre strade:
  - lo ricava da `ctx.tocca`, che il contratto non nomina;
  - lo ricava da `ctx.chi`, il nome di chi è di turno, che il contratto dà: si cerca la sua
    posizione in `ctx.giocatori`, che è scomodo;
  - lo tiene anche nei dati, come fa il riferimento `prove/giochi/tris` con `segno`. Così ci sono
    due fonti dello stesso fatto.
- **I punti al Giocatore 1 senza turni.** In una fase con `turni: false`, se non si sa chi ha
  mosso (nessun legame di voce o di schermo), `risultato` dà i punti numerici a `S0.tocca`
  (`motore_gioco.js:821`), che lì resta sempre 0. Anche `ctx.chi` è il nome di `S.tocca`. Il
  contratto dice «i punti vanno a chi ha mosso, se si sa»: quando non si sa, vanno in silenzio al
  Giocatore 1. È da segnare in #197 o nella parte 2.

**Tre testi suggeriscono l'esito a ogni mossa:**
- il contratto (`contratto.py`, prima riga del §2: «turni, punti, esito di ogni mossa», #197);
- il prompt dell'analisi prima del codice (`accettazione.SISTEMA_GIOCO`: «dopo ogni mossa di
  solito c'è la fase «esito»»; #197 cerca nel contratto, nel prompt del gioco, nella partenza e
  nei vincoli, ma questo prompt non è tra quelli che nomina);
- la **partenza**: il gioco d'esempio delle porte dà `esito` a ogni mossa, e il suo
  `gioco.test.js` controlla la fase «esito» e «avanti» dopo la prima mossa.

Per le porte è giusto: ogni porta rivela qualcosa. Per un tris è la forma sbagliata, ed è quella
che l'agente ha scritto il 20/10 sera (L3: `esito: "Mossa effettuata"`).

### 3.2 I caratteri

Misurati con `len()` sul codice di `b032cd41`, con la Config predefinita. I token sono stimati con
il rapporto 3,47 caratteri per token di Qwen3.6, misurato l'11/10.

| Testo | Caratteri | Token (stima) |
|---|---|---|
| Prompt intero del gioco (`sistema_estensione(gioco=True)`: `SISTEMA_GIOCO`, contratto, partenza, `ANTI_INIEZIONE`) | 16 243 | ~4 700 |
| `SISTEMA_GIOCO` | 2 213 | ~640 |
| Contratto del gioco (`contratto.testo(tipo="gioco")`) | 12 592 | ~3 630 |
| di cui il §2, la scheda e la macchina (`scheda_testo`, 15 voci) | 9 141 | ~2 630 |
| Paragrafo della partenza nel prompt | 831 | ~240 |
| I quattro file di partenza (letti una volta: manifesto 767, logica.js 1 275, logica.test.js 725, gioco.test.js 1 631) | 4 398 | ~1 270 |
| Prompt dell'analisi prima del codice per un gioco (`accettazione.SISTEMA_GIOCO`) | 1 989 | ~570 |

**Il §2 per argomento.** La classificazione è mia: per ogni voce, se resterebbe in un'interfaccia
senza fasi.

| Voci del §2 | Caratteri | Con un'interfaccia senza fasi |
|---|---|---|
| Concetti della macchina: l'introduzione (684), il manifesto con `macchina` (450), la preparazione (697), fasi, turni, verso e pagine (748), la forma di una mossa (766), `g.stato()` (653) | 3 998 | spariscono o si riducono a poche righe |
| `attivi`, `vista` e caselle (759) | 759 | resta circa metà (la vista e le caselle) |
| Comandi a voce (780), giocatori e nomi (684), tela (862) | 2 326 | restano: sono garanzie di Calliope |
| Generici: file e test (772), il caso (393), tetti (159), vietato (454), gioco puro (265) | 2 043 | restano |

La prima riga è generosa. Metà della voce «fasi» è l'elenco dei modelli di pagina, che C tiene;
l'introduzione parla anche di riquadro, palco e voce; la voce del manifesto resta in gran parte.
Contando solo ciò che sparisce davvero, **circa 3 300–3 500 caratteri su 9 141 (36–38 %) parlano
soltanto della macchina**: ~1 000 token per passata nel prompt di sistema, in cache. Il costo vero non è la lunghezza, è il numero di regole
che un modello piccolo deve tenere insieme. La ricerca del 19/10 (§ 1) lo dice dai numeri: le
contromisure in prosa si ripresentano in forma nuova, quelle per costruzione chiudono la loro
famiglia.

### 3.3 Gli errori dei banchi e dei casi veri dal 13/10 (catalogo)

Ogni riga è un lavoro di gioco **non riuscito**. Fonte: la voce d'area o la issue citata. Le
etichette dell'attribuzione:
- **M**: concetto della macchina come causa principale;
- **M?**: probabile, da verificare;
- **Mv**: misto, logica del modello e forma della vista o del palco;
- **T**: la transizione dai giochi del formato di prima, finita il 14/10;
- **H**: l'harness;
- **?**: causa non scritta.

| Data, banco | Lavoro | Cosa | Fonte | Attribuzione |
|---|---|---|---|---|
| 14/10 notte, banco `agente-tetto-2` (porte, correzione di un gioco del formato di prima) | L1 | 5 passate a vuoto ragionando su `calliope.fase` della prova di fumo e su `gioco.js` | agenti-estensioni, «Il banco del 14/10» | T |
| idem | L7 | `g.comando("porta", 1)` nei suoi test; il motore: «"dopo" è la fase dopo l'esito» | idem | T + M |
| idem | L10 | tre passate a vuoto «forse c'è un require»; accettazione nascosta verde, nessuna consegna | idem | T (+ H, poi chiuso) |
| 14/10 sera, banco `agente-valori` (porte) | L7 | `g.comando("avanti")` subito dopo «2 giocatori»; `stato.punti["Giocatore 1"]`; poi «corregge» la macchina: `dopo: "esito"`, la fase «esito» dichiarata | agenti-estensioni, «Il banco del 14/10 sera» | M |
| idem | L10 | «avanti» dopo i giocatori; una fase «preparazione» sua con un comando «giocatore» | idem | M |
| 18/10, caso vero (tris per due, S32, 5 giri, 149 000 token) | L1 | i suoi test non uscivano dalla preparazione (min = max: solo «Inizia»); ore a cambiare `min` e la fase «preparazione» nel manifesto. In più la specifica rimasta «Python con Pygame» e i requisiti principali tutti `si_puo: false` | #174 | M (+ H: firma dell'errore, novità, specifica) |
| 20/10 mattina, `giri-1020-1018` (porte, 2 giri) | L4 | un `apriGioco` suo in gioco.test.js (motore finto), con logica.js giusto | #192: «regressione di #186, sicura» (la frase «apriGioco c'è già» sparita dal prompt della correzione) | H (su un'API dei test ricca; chiusa da #192) |
| idem | L6 | lo stesso, più la tappa con tutto verde che non chiudeva | #192 | H |
| idem (tris2) | L1 | il segnaposto della compattazione scritto come gioco.test.js; rossi di logica e di forma della vista | #192 | H + Mv |
| idem (tris2) | L3 | il suggerimento del palco sbagliato con la pagina già «griglia»; rossi di logica e di vista | #192 | Mv |
| idem (tris2) | il terzo | «i rossi dei tre tris sono del modello (logica, forma di `vista`)» | #192 | Mv |
| 20/10 sera, `giri2-1020-1753` (tris2) | L3 | un esito a ogni mossa («Mossa effettuata»); 0 esempi dall'analisi | #197 | M (+ H: l'analisi) |
| idem | L5 | `TypeError … reading 'punti' [in logica.js:62]`, indice di un giocatore sbagliato | #197 | M? (vedi `turno` al § 3.1) |
| idem | L1 | 8 esempi rossi su 13 (requisiti 3, 4, 5), 4 passate a vuoto | #197 | ? |

**Il conto.** Su 14 lavori di gioco falliti:
- un concetto della macchina è la causa principale in **4 certi** (14/10 sera L7 e L10, 18/10
  L1, 20/10 sera L3) **e 1 probabile** (20/10 sera L5). C'è anche il «dopo» di 14/10 notte L7,
  dentro la transizione;
- un'interfaccia senza fasi toglierebbe quindi **5–6 di questi 14**;
- la transizione dai giochi di prima conta 3 lavori, e non c'è più;
- la regressione dell'harness (#186, chiusa da #192) conta 2 lavori. Il motore finto è stato
  possibile perché i test passano da un'API ricca, ma la causa è l'harness;
- i tre tris del 20/10 mattina sono la logica del modello e la **forma della vista**. La vista
  resta anche in C: non sostengono C, sono il rischio che il § 5 gli assegna;
- un lavoro ha la causa non scritta.

**Cosa invece è andato bene.**
- La correzione delle porte, cioè un gioco che c'è già con la forma giusta. Dal 19/10 fa
  **14/16**: 5/5 il 19/10, 1/3 a due giri il 20/10 mattina (i due rossi sono L4 e L6), 3/3 a due
  giri e 5/5 a un giro il 20/10 sera. Dopo #192 fa **8/8**.
- Il 20/10 mattina l'accettazione nascosta era verde al primo giro in 5 lavori su 6, quindi in
  almeno due tris su tre. Quell'accettazione però ha due soli test, la partenza e una vittoria in
  riga (§ 7): dice che l'agente scrive una vittoria in riga, non che l'algoritmo intero c'è.

I fallimenti con la macchina stanno quasi tutti nel **`gioco.test.js` dell'agente**, scritto con
`apriGioco`: 14/10 notte L7, 14/10 sera L7 e L10, #174 L1, #192 L4 e L6. Solo #197 L3 sta in
`logica.test.js`. È il punto debole che la ricerca del 19/10 trova in tutto il catalogo, i test
scritti dall'agente. Qui li scrive contro un'API ricca (fasi, `g.stato()`, «avanti»), e ogni regola
che indovina male li rende rossi. Da qui viene la variante `tris2-solo-logica` del § 5 (A′).

## 4. Cosa copre già l'harness di oggi

| Cosa | Da quando | Copre | Per un gioco senza fasi |
|---|---|---|---|
| Prova di fumo nel DOM finto, poi per fasi, poi con il palco | 05/10, 13/10, 14/10 | eccezioni con file:riga, forma sbagliata, stati senza uscita, partite che non finiscono, palco | resta, con l'esploratore sugli stati invece che sulle fasi |
| `apriGioco` e il test del disegno | 12/10 sera | la classe del 12/10 (logica e disegno scollegati) | resta per Calliope; l'agente può testare le funzioni pure |
| Riproduzione, test due volte, semi, `esegui_js` | 12/10 sera | correzioni non riprodotte, test col caso, debug a mente | uguale |
| Esempi di accettazione in sola lettura (anche per i giochi) | 13/10 | i test dell'agente che ereditano le sue ipotesi | più semplici (niente «fase») |
| Manifesto subito, «tutto verde» vuol dire consegnabile | 14/10 sera, #180 | il manifesto rotto saputo solo alla consegna | uguale |
| Porte oneste | #180, 19/10 | falsi «fatto»: esito fuori dall'enum, prosa, consegna rossa, riproduzione di struttura | uguale |
| Strumenti onesti | #185, 19/10 | giri in tondo, uscita troncata, test rifatti senza cambiare niente, riletture | uguale |
| Partenza già verde, prompt per tipo | #186, 19/10 | il gioco ricopiato dal prompt (#174), il 45 % del prompt per Python | uguale, con file più piccoli |
| `apriGioco` c'è già, tappa consegnabile, segnaposto | #192, 20/10 | il motore finto, la tappa verde che non chiude | il motore finto non ha più un'API da imitare |
| Banco del revisore | #182, 19/10 (solo banco) | «è il test o è il codice?»: 24/25 sui casi di quel tipo | uguale |

**Che cosa nel 13/10 copriva solo la macchina, e oggi?**
- La classe del 12/10 (logica e disegno scollegati) la coprono il disegno di Calliope e,
  indipendentemente, `apriGioco` e gli esempi.
- Le costanti doppie e il `require` li coprono il file solo e il controllo della consegna.
- I gestori che lanciano e la preparazione con i nomi vuoti li copre il motore che disegna.
- I giri a vuoto del gioco.js riscritto li coprono gli strumenti onesti e `modifica_file`.

Resta della macchina sola il **disegno** di Calliope, con la preparazione e l'istantanea, e nessuno
dei tre ha bisogno delle fasi del gioco.

## 5. Le opzioni

In tutte: niente migrazioni dei giochi vecchi (Calliope non è in produzione), e la tela come via
libera per il tempo reale.

### A. La macchina com'è, con il contratto semplificato

- **Cosa cambia.**
  - Il §2 riscritto con una regola per concetto e con le incoerenze del § 3.1 tolte: `tocca` con un
    significato solo, `turno` spiegato o tolto dal contesto della mossa, l'esito «quando una mano
    finisce» (#197).
  - Il prompt dell'analisi corretto.
  - Una partenza che non insegni l'esito a ogni mossa: per esempio senza esito nelle mosse normali,
    e con la fine che dice il risultato.
- **Cosa perde Calliope:** niente.
- **Cosa guadagna l'agente:** meno contraddizioni. I concetti restano tutti: fasi, tre forme di
  mossa, preparazione nei test, `g.stato()`.
- **Rischi.** È una correzione in prosa: il catalogo dice che si ripresentano in forma nuova
  (preparazione il 18/10, esito il 20/10). Poi c'è la tentazione di partenze per famiglia di gioco
  («una partenza a griglia per il tris»): risolve il caso, non il principio.
- **Lavoro:** 0,5–1 giorno, in gran parte dentro #197.

### A′. La macchina com'è, e l'agente scrive solo i test della logica (`tris2-solo-logica`)

- **Cosa cambia.** È l'alternativa più economica, e la suggerisce il catalogo (§ 3.3): quasi tutti
  i fallimenti con la macchina stanno nel `gioco.test.js` dell'agente. Con A′:
  - l'agente scrive solo `logica.test.js`, sulle funzioni di `GIOCO.mosse`, `attivi` e `vista`;
  - la partita la coprono la prova di fumo per fasi e gli esempi di accettazione;
  - `gioco.test.js` resta di Calliope, oppure non c'è.

  La classe del 12/10 per cui `gioco.test.js` era nato (logica e disegno scollegati) è chiusa per
  costruzione dal disegno di Calliope (§ 4).
- **Cosa perde Calliope:** niente delle garanzie. Perde il test del disegno scritto dall'agente:
  nelle correzioni la riproduzione di un difetto visibile va scritta come test della logica, o
  come esempio.
- **Cosa guadagna l'agente:** niente preparazione, «avanti», `g.stato()` né motore finto nei suoi
  test. I concetti della mossa (`esito`, `dopo`, fasi) restano.
- **Rischi:** le riproduzioni delle correzioni dei giochi oggi vogliono `gioco.test.js` con
  `apriGioco` (`VINCOLO_CORREZIONE_GIOCO`), quindi vanno ripensate.
- **Lavoro:** mezza giornata (prompt, contratto, partenza e vincolo della correzione).
- **Perché misurarla:** separa «l'API dei test» da «l'interfaccia». Senza A′, un buon risultato di
  C non direbbe quale delle due cose ha aiutato.

### B. Una macchina più piccola

- **Cosa cambia.** Il motore tiene ancora turni e punti, ma con meno concetti:
  - una fase implicita «gioco» quando il manifesto dichiara solo `comandi`; le fasi in più restano
    possibili, senza `verso`;
  - la mossa restituisce `{ dati, punti?, messaggio?, fine?, ancora? }`: niente `fase` né `dopo`;
  - il messaggio non è una fase che blocca: si mostra con la pagina dopo, e «avanti» sparisce dal
    gioco;
  - `fine` è il testo del risultato;
  - `tocca` sempre una posizione, `ctx.turno` tolto o chiamato `giro`;
  - `apriGioco` parte già dalla partita di serie, e la preparazione si prova solo se la si chiede.
- **Cosa perde Calliope:** la fase «esito» che blocca le mosse e va avanti da sola dopo
  `esito_s`; il controllo di `verso`.
- **Cosa guadagna l'agente:** la forma della mossa in una riga; niente preparazione nei test;
  niente «avanti».
- **Rischi.**
  - Resta un'API propria (`dati` dentro il risultato, `punti` «a chi ha mosso», `ancora`).
  - Chi muove sta ancora in due posti (motore e dati) per i giochi che devono sapere il segno.
  - Il motore finto resta possibile: i test dell'agente passano ancora da `apriGioco`.
- **Lavoro: 2–4 giorni.**
  - motore (`controlla`, `risultato`, `attivi` e la fase implicita) e `macchina.normalizza`;
  - contratto, partenza e prompt dell'analisi;
  - i giochi delle prove (`porte`, `porte_fasi`, `tris`, `pagine`, `ostile`, `segnali`) e circa
    20 file di prova che li usano (`prova_gioco_macchina`, `prova_gioco_stato`,
    `prova_gioco_palco`, `prova_giochi_pagina`, `prova_partenza_gioco`…);
  - i casi del banco.

### C. Un'interfaccia minima, da cui Calliope ricava il resto

- **Cosa cambia.** Lo stato è del gioco. L'agente scrive quattro funzioni pure su un oggetto suo.
  Calliope ne ricava istantanea, voce, giudice, palco e partite condivise. Bozza qui sotto.
- **Cosa perde Calliope.**
  - **Turni e punti coerenti per costruzione**: li scrive il gioco nel suo stato, e Calliope
    controlla la forma, i tetti e il passaggio del turno (§ C.4).
  - **La validazione per fase** dei comandi, che diventa «tra i comandi dichiarati».
  - **Pagina e turni per gioco, non per fase.** Oggi ogni fase sceglie la sua pagina («scelte» per
    una categoria, poi «griglia») e i suoi turni (un voto simultaneo dentro un gioco a turni). La
    facciata a una fase non lo permette, e restituire la pagina con la vista non passa
    dall'adattatore: `normalizza` del motore fissa la pagina per fase. È una perdita vera di
    espressività.
  - La fase «esito» che blocca non è persa: c'è un campo facoltativo `messaggio` (§ C.2) che
    l'adattatore traduce in `{ esito, dopo: "gioco" }`. Salva i giochi a rivelazione (le porte),
    e nel caso normale il concetto non c'è.
  - **`ancora` della mossa** («lo stesso giocatore muove di nuovo») è implicito in `tocca`.
    «Ancora» della fine resta: è della fase «fine» di Calliope.
- **Cosa guadagna l'agente.**
  - Quattro funzioni e tre campi fissi, nella forma di un esercizio di JavaScript.
  - **I suoi test sono chiamate di funzione** (`nuovaPartita`, poi `mossa`, poi un `assert`):
    niente preparazione, niente «avanti», niente `g.stato()`, nessun motore da imitare.
  - Il §2 scende a circa 4 000–4 500 caratteri (stima).
- **Rischi.**
  - L'errore si sposta sulle parti di Calliope che restano: la forma della vista e delle caselle,
    i comandi nel manifesto. Il 20/10 mattina la vista è già stata un errore.
  - Un gioco che sbaglia `tocca` fa dire a Calliope «Tocca a Bruno» quando tocca ad Ada. Lo
    prendono gli esempi (`tocca` dopo una mossa) e un controllo nel motore.
  - Chi muove resta in due posti, lo stato dell'agente e `S.tocca` del motore, tenuti allineati
    dall'adattatore (§ C.4). All'agente è nascosto, ma è lo stesso rischio imputato a B.
  - Rifarlo in modo nativo butta via il nucleo del 13–15/10. Per questo la bozza è una
    **facciata** (§ C.6).
- **Lavoro.**
  - Come facciata sopra il motore di oggi: **2–3 giorni** di prototipo, più le prove. Comprende:
    - l'adattatore;
    - la **riscrittura dei messaggi d'errore** nel vocabolario della facciata (§ C.6);
    - `scheda.normalizza` che sintetizza `macchina`;
    - `_controlla_gioco`, `accettazione.SISTEMA_GIOCO` e gli esempi (`fase` → `finita`);
    - contratto, partenza e caso del banco.
  - Come motore nativo senza fasi: **5–8 giorni** (il nucleo `crea`, `macchina.py` e il server,
    l'esploratore, l'accettazione, i giochi delle prove e circa 20 file di prova). Stima incerta.

#### C.1 Il manifesto

```json
"scheda": {"tipo": "gioco", "file": ["logica.js"], "giocatori": {"min": 2, "max": 2},
  "pagina": "griglia", "turni": true, "condivisa": false, "giocatore": false,
  "comandi": {"casella": {"forme": ["casella {n}", "{n}"], "n": {"da": 1, "a": 9},
                          "etichetta": "Casella {n}"}}}
```

`comandi` ha la sintassi di oggi (forme, slot, dominio, etichetta). Validazione, riservate,
doppioni e domande di Calliope restano quelli di `macchina._comando` e `ascolta`. `pagina` è uno
dei sei modelli (o «tela»), per tutto il gioco. `turni` di serie è vero.

#### C.2 Le funzioni (logica.js)

```js
const GIOCO = {
  // Lo stato è tuo: un oggetto JSON (≤ 16 000 caratteri). Calliope legge solo tre campi:
  //   tocca: la posizione di chi muove (0, 1, …); con "turni": false non c'è
  //   punti: un numero per giocatore
  //   fine:  false, oppure il testo del risultato («Ha vinto X», «Pareggio»)
  nuovaPartita({ giocatori, nomi }) {
    return { tocca: 0, punti: Array(giocatori).fill(0), fine: false, celle: Array(9).fill("") };
  },
  // I comandi che valgono adesso, dentro quelli del manifesto ({} a partita finita)
  comandi(stato) { return { casella: libere(stato.celle) }; },
  // La mossa: lo stato nuovo. Arriva solo un comando che `comandi` dà per valido
  mossa(stato, { comando, valore, chi }) { /* … */ return nuovo; },
  // Cosa mostrare: solo testi, e le caselle nella pagina «griglia»
  vista(stato, { nomi }) { return { titolo: "Tris", testo: `Tocca a ${nomi[stato.tocca]}`, caselle }; },
  // facoltativi: entra(stato, { nuovo }) → stato; tela(area, stato, tela) con "pagina": "tela";
  // nello stato, messaggio: un testo da mostrare qualche secondo prima di continuare (le porte:
  // «Dietro la 3 una zucca!»), poi Calliope lo toglie. Per una mossa normale non c'è
};
if (typeof module !== "undefined") module.exports = { GIOCO };
```

I test dell'agente:

```js
let s = GIOCO.nuovaPartita({ giocatori: 2, nomi: ["Ada", "Bruno"] });
s = GIOCO.mossa(s, { comando: "casella", valore: 1 });
assert.strictEqual(s.tocca, 1);
```

#### C.3 Che cosa fa Calliope, cioè il motore come involucro

- **Preparazione e fine.** La preparazione di oggi («Inizia», «N giocatori», «gioco anch'io», i
  nomi) avviene prima di `nuovaPartita`. Con `fine` a testo, Calliope mostra il risultato e poi
  la classifica con «Ancora», che rifà `nuovaPartita`.
- **Istantanea**, invariata per il server: `{ n, fase, tocca, turno, giocatori: [{ nome, punti,
  scritto?, schermo?, voce? }], esito, comandi }`.
  - `n` lo tiene Calliope;
  - `fase` vale «preparazione», «gioco», «esito» o «fine». Passa per «esito» perché la fine e il
    `messaggio` si traducono con `esito` (§ C.6). La classifica non mostra il testo del risultato
    (lo cancella la fase «fine», `motore_gioco.js:790`): si vede nei secondi dell'esito, come oggi;
  - `tocca` e i punti vengono dai campi dello stato;
  - `esito` è il testo di `fine`;
  - `comandi` sono i piatti di `comandi(stato)`.
  - `valida_istantanea` e `per_fase` vedono una fase sola, «gioco», con i comandi dichiarati più
    «gioco anch'io».
- **Voce**: l'elenco piatto di `macchina.ascolta` dai `comandi` del manifesto. Restano uguali la
  regola `gioco_comando`, la finestra senza nome e «chi approva sente» («si gioca a voce o
  toccando, con un comando»).
- **Giudice**: invariato. Legge i comandi attivi dell'istantanea e le loro forme.
- **Domande standard**: invariate. Leggono l'istantanea, che ha la stessa forma.
- **Chi muove**: invariato su `tocca`. Con `"turni": false` muove chiunque, e i punti li scrive il
  gioco.
- **Palco**: il modello di pagina del manifesto. La vista dà testi e caselle, i pulsanti vengono
  dai comandi attivi che non sono in una casella (come `pagina(S)` oggi), la misura «fuori dal
  palco» resta.
- **Partite condivise e ripresa**: la ripresa è `{ n, nomi, legami, stato }`. Lo specchio disegna
  `vista(stato)`, come oggi `nucleo.riprendi` e poi la pagina.

#### C.4 I controlli di Calliope dopo ogni mossa (al posto di `controlla`)

- lo stato è un oggetto serializzabile entro il tetto;
- `punti` ha un numero finito per giocatore;
- `fine` è `false` o un testo di al più 160 caratteri;
- `comandi(stato)` sta dentro il manifesto;
- con `turni`, `tocca` resta a chi ha mosso o passa al giocatore dopo.

Un errore dice funzione, comando e valore, come gli errori del motore di oggi. Nella prova di fumo
uno stato non finito senza comandi attivi è uno stallo, e una partita che non finisce in 500 passi
è un errore. Resta una nota, non un errore, se `tocca` non cambia mai in un gioco a turni con più
giocatori.

#### C.5 Esempi di accettazione

Restano in forma chiusa: giocatori, mosse, poi in `atteso` `tocca`, `punti`, `attivi`,
`non_attivi`, `finita` (sì o no) e `testo`. Il codice li trasforma in un test che usa
`apriGioco` (la strada di Calliope), oppure le funzioni pure.

#### C.6 C come facciata sopra la macchina di oggi

C si può realizzare **senza cambiare lo stato e il disegno del motore**. Un adattatore, scritto una
volta e condiviso da riquadro, `fumo_js.mjs`, `apriGioco` e sandbox, trasforma il `GIOCO`
dell'agente in un `GIOCO` della macchina a una fase.

| La facciata (dell'agente) | La macchina (di oggi) |
|---|---|
| i `comandi` del manifesto | una fase «gioco» con quei comandi, tradotta da `scheda.normalizza` |
| `comandi(stato)` | `attivi.gioco` |
| `mossa` | `mosse.gioco[c]` che restituisce `{ dati: nuovo, punti: delta, ancora: nuovo.tocca === vecchio.tocca }`; con `fine` a testo `{ dati, punti, esito: fine, dopo: "fine" }` |
| `vista` | `vista.gioco` |

Con il `messaggio` dello stato la mossa diventa `{ dati, punti, esito: messaggio, dopo: "gioco" }`.
Con la pagina «tela» va tradotto anche `tela.esci`.

Server, voce, giudice, palco, partite condivise, ripresa e legami restano quelli di oggi.

**Cosa non è gratis: gli errori.** Dicono tutti la lingua della macchina:
- `controlla`, `attivi`, `vista` e `casella` del motore («GIOCO.vista.gioco.caselle[r][c]»,
  «esito con dopo: "fine"», «verso nel manifesto»);
- l'esploratore della prova di fumo (`fumo_js.mjs`, `esplora`);
- `apriGioco` («avanti vale solo nella fase esito»).

Un agente che conosce solo `nuovaPartita`, `comandi`, `mossa` e `vista` riceverebbe errori su
un'API mai vista, proprio dove il catalogo dice che conta la diagnosi con il nome giusto. Ci sono
due strade:
- l'adattatore cattura e riscrive gli errori («mossa(stato, casella 3) restituisce punti di
  lunghezza 1, ne servono 2»);
- il motore riceve un vocabolario per i suoi messaggi.

Con le parti Python questo porta il prototipo a 2–3 giorni.

L'altro limite: `tocca` deve restare o passare al giocatore dopo, perché il motore fa +1. È lo
stesso controllo del § C.4. È la via più economica per **misurare** C, e se il banco la conferma
può anche restare l'implementazione.

### D. JavaScript libero con la sola prova di fumo

- **Cosa cambia:** gioco.js e logica.js liberi come l'11/10.
- **Cosa perde Calliope:** quasi tutto quello che c'è dal 13/10, salvo rifarlo in un altro modo:
  - comandi a voce dalla macchina (si torna ad `ascolta` piatto e `quandoComando`);
  - istantanea, domande standard, giudice;
  - palco e misura;
  - partite condivise con un motore solo, ripresa, chi è quale giocatore;
  - esempi di accettazione dei giochi, che senza un contratto stabile non si scrivono.
- **Cosa guadagna l'agente:** il terreno che conosce.
- **Rischi:** tornano le cause dell'11–12/10 (`require`, costanti doppie, gestori, logica e
  disegno scollegati), cioè proprio quelle che la macchina ha chiuso per costruzione.
- **Lavoro:** togliere costa poco (1–2 giorni), rifare la voce e il disegno costa molto.
- **Uso:** solo come riferimento della misura (`tris-nudo`), non come formato.

### Confronto

| | A | A′ (solo logica) | B | C (facciata) | D |
|---|---|---|---|---|---|
| Concetti per l'agente | ~14 voci, meno contraddizioni | ~11 (via l'API dei test) | ~9 | ~5 (4 funzioni, 3 campi) + comandi e vista | JavaScript + DOM + voce a mano |
| §2 del contratto (stima) | ~8 000 | ~7 500 | ~6 000 | ~4 000–4 500 | — |
| Test dell'agente | `apriGioco`, fasi, preparazione | funzioni della logica | `apriGioco` senza preparazione | chiamate di funzione | liberi |
| Cosa perde Calliope | niente | il test del disegno dell'agente | l'esito che blocca, `verso` | validazione per fase; pagina e turni per gioco; turni e punti controllati, non costruiti | quasi tutto |
| Lavoro del 13–15/10 | tenuto | tenuto | tenuto in gran parte | tenuto (il motore sotto) | perso |
| Lavoro | 0,5–1 g | 0,5 g | 2–4 g | 2–3 g prototipo | 1–2 g, più la voce da rifare |
| Rischio principale | la prosa si ripresenta | le riproduzioni dei giochi da ripensare | API propria, chi muove in due posti | l'errore si sposta sulla vista; errori del motore da tradurre | le cause dell'11–12/10 |

## 6. Raccomandazione

1. **Chiudere #197 prima di misurare**, con in più il prompt dell'analisi e l'esempio della
   partenza (§ 3.1), e la terza incoerenza: i punti al Giocatore 1 senza turni. Il tris2 0/3 è
   stato misurato con un contratto che diceva la cosa sbagliata.
2. **Il banco della parte 2 con tre casi, a 10 ripetizioni** (§ 7): `tris2`, `tris2-solo-logica`
   (A′) e `tris-nudo`.
   - A′ costa mezza giornata e prova l'ipotesi più economica del catalogo: il costo sta nell'API
     dei test dell'agente, non nell'interfaccia del gioco.
   - `tris-nudo` dà il tetto del modello, cioè la misura che manca alla tesi di chi amministra.
3. **Il prototipo di C come facciata** (§ C.6, 2–3 giorni) **solo se la misura lo indica**:
   `tris-nudo` alto, mentre `tris2` e `tris2-solo-logica` restano bassi. Allora un quarto caso,
   `tris-facciata`, con la stessa accettazione di `tris2`. C è l'unica opzione che toglie insieme i
   concetti della mossa e l'API dei test, ma tutti i fallimenti che toglierebbe sono 5–6 su 14. La
   vista resta, e i tre tris del 20/10 mattina dicono che lì l'errore c'è già.
4. **Dopo il banco**, se C vince, una decisione nuova, perché cambia il formato dei giochi:
   facciata come implementazione, o motore semplificato. B resta il ripiego, se C sposta
   l'errore sulla vista senza guadagno.

## 7. Il banco che decide (parte 2)

**I casi.** Stesso compito, stessa semantica dell'accettazione nascosta. Gli stessi giri (2), le
stesse passate per giro, la stessa temperatura e lo stesso presence della Config. **10
ripetizioni per caso, obbligatorie**: con 5, anche 4/5 contro 2/5 non si distingue dal caso
(Fisher esatto a due code, p ≈ 0,52), e 8/10 contro 3/10 dà p ≈ 0,07.

| Caso | Ambiente | Accettazione nascosta |
|---|---|---|
| `tris2` (oggi, dopo #197) | la macchina, il contratto di oggi | via `apriGioco`: preparazione e «Inizia», mosse, vittoria in riga, colonna e diagonale, pareggio, casella occupata (non più attiva), a chi tocca dopo una mossa |
| `tris2-solo-logica` (A′) | la macchina di oggi; l'agente scrive solo `logica.test.js` sulle funzioni di `GIOCO` (prompt, contratto e partenza senza `gioco.test.js`) | **la stessa** di `tris2` |
| `tris-nudo` | un file JavaScript con funzioni dai nomi dati nel compito (`nuovaPartita`, `mossa`, `vincitore`) e test `node --test`; niente macchina, contratto dei giochi, manifesto, voce o palco | le stesse regole sulle funzioni (la preparazione lì non c'è) |
| `tris-facciata` (solo se le regole qui sotto lo chiedono) | la facciata del § C.6 sopra il motore di oggi | **la stessa** di `tris2`, via `apriGioco` |

**Le partenze pareggiate.** Oggi `tris2` parte dalle porte, che insegnano l'esito a ogni mossa.
Se una variante partisse da un gioco a griglia, il banco misurerebbe la partenza e non
l'interfaccia. Quindi tutti i casi partono dallo stesso gioco d'esempio, le porte o un gioco
neutro, scritto nella forma del caso. Dopo #197 le porte della partenza non hanno più l'esito a
ogni mossa.

**Cosa misurare per lavoro**, nella riga di `riepilogo.json` com'è dopo #9:
- riuscito e accettazione nascosta verde;
- il giro della consegna (anche alla tappa);
- passate, token e minuti;
- i rossi dei test dell'agente alla fine e la **firma del primo errore**, per dire «di macchina»,
  «di API dei test», «di vista» o «di logica» dai dati e non a mano;
- le regole scattate (`agente_motore_finto`, `agente_stato_gia_visto`, `agente_consegna_alla_tappa`);
- gli esempi dell'analisi e i tolti.

**Le soglie, scritte prima di girare.** Alto vuol dire ≥ 8/10, basso ≤ 3/10. Le regole si
applicano in quest'ordine, e vale la prima che si avvera:
1. **`tris2` alto:** basta A (#197). Gli altri casi restano come misura, senza cambiare formato.
2. **`tris2-solo-logica` alto e `tris2` basso:** il costo era l'API dei test. Si fa A′ (una PR),
   niente C.
3. **`tris-nudo` basso:** il limite è il modello o l'harness generico, non la macchina. Si tiene A
   e si guarda #175.
4. **`tris-nudo` alto, `tris2` e `tris2-solo-logica` bassi:** il costo è dell'interfaccia. Si fa il
   prototipo e `tris-facciata` a 10 ripetizioni:
   - alto: C, con una decisione nuova;
   - basso: il costo sta nelle parti che restano (vista, comandi), e si torna ad A sui punti
     trovati dalle firme degli errori.
5. **Il caso intermedio** (un caso fra 4/10 e 7/10, o due casi a meno di 5 punti su 10 l'uno
   dall'altro): nessuna decisione. Si leggono le firme del primo errore per classe e si
   rigirano i due casi in dubbio con altre 10 ripetizioni. Una sola volta: se resta intermedio,
   vale la regola 1 con A.

**Cautele.**
- **`tris-nudo` misura un tetto, non un'alternativa:** non ha voce, palco, manifesto né
  accettazione via `apriGioco`. La differenza `tris2` − `tris-nudo` è il costo di tutto il nostro
  ambiente. A′ e la facciata ne separano le parti.
- **L'accettazione nascosta di `tris2` oggi è debole:** due test, la partenza e una vittoria in
  riga. Va allargata alle regole della issue per tutti i casi allo stesso modo, prima di girare.
- **L'analisi prima del codice** (gli esempi visibili) va tenuta uguale: in tutti i casi, il nudo
  con un suo schema, oppure in nessuno (`--accettazione no`). Altrimenti la tappa consegnabile
  chiude d'ufficio in un caso e non nell'altro.
- **Le porte come controllo del contrario**, solo se si arriva a `tris-facciata`. Si fanno con il
  `messaggio` della facciata (§ C.2), così l'esito che blocca resta. Ci vuole il «prima» da
  correggere scritto nella forma C, perché oggi esiste solo nella forma della macchina.
  L'accettazione va adattata o tenuta solo dove vale: `ACCETTAZIONE_PORTE` cerca «+ 3 punti», che
  oggi scrive la pagina dell'esito del motore (`S.esito.punti`), e con il `messaggio` va
  verificato che ci sia ancora. Senza queste due cose le porte in forma C restano fuori dal banco.

## 8. Cosa non so

- **Le cause dei fallimenti** le ho prese dai rapporti scritti (voci d'area, issue #174, #192,
  #197), non dai registri dei lavori sulla DGX. Per i tre tris del 20/10 mattina «logica e forma
  della vista» non dice quanto pesi l'una e quanto l'altra. Per L1 del 20/10 sera la causa non è
  scritta.
- **Il `TypeError` di L5** con `ctx.turno` usato come posizione è un'ipotesi coerente con il
  codice, non una verifica.
- **Quanto sappia fare il modello fuori dal nostro ambiente** non è mai stato misurato: è
  `tris-nudo`. L'accettazione verde del 20/10 mattina ha due test e non dice che l'algoritmo
  intero c'è.
- **Se un'interfaccia più piccola sposti l'errore invece di toglierlo** (sulla vista e le caselle,
  sui comandi del manifesto). È il rischio principale di C, e solo il banco lo dice.
- **Token**: sono stime con 3,47 caratteri per token; il tokenizer di Qwen3.6 sulla DGX darebbe i
  numeri veri.
- **Il lavoro di C** è stimato largo: 5–8 giorni per il motore nativo, 2–3 per la facciata con la
  traduzione degli errori. Il secondo presume che il server non vada toccato.
