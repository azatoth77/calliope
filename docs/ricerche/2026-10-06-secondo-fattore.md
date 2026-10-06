# Secondo fattore per chi amministra: telefono, sfida e chiave vocale (06/10/2026)

*Progetto, non codice: congelamento delle funzionalità attivo (`docs/roadmap.md`). Chiude, quando
sarà realizzato, il rischio «la voce come unico fattore per chi amministra» delle due analisi del
06/10 (`2026-10-06-analisi-complessiva.md` C2, `2026-10-06-analisi-2.md` § 5, rischio 5).
Direzione approvata da Dario il 06/10; i punti aperti sono in § 14.*

## 0. In breve

| Strato | Cosa prova | Contro che cosa | Già c'è? |
|---|---|---|---|
| **Voce** (CAM++ sopra soglia, nella frase) | chi parla, probabilmente | ospiti, familiari, TV con altre voci | sì |
| **Sfida a parole casuali** (`conferme.Sfida`) | che chi parla è **presente adesso** | registrazioni, TV, audio rifatto | sì |
| **Telefono** (tocco su «Approva» nel telefono abbinato di chi amministra) | **possesso** di un oggetto separato | voce clonata in tempo reale, satellite compromesso, chi è nella stanza | no |
| **Chiave vocale** (5 parole segrete, se ne chiedono 2 a caso) | **conoscenza** di un segreto | registrazioni e cloni fatti da audio vecchio, telefono rubato o lasciato sbloccato | no |

Scelte principali:

1. **Chi amministra deve avere un telefono e uno schermo personale abbinati** (requisito di Dario
   del 06/10). Senza, le azioni «di fiducia» restano bloccate (§ 5); il registro delle capacità lo
   dice (§ 9).
2. Le azioni si dividono in tre gradini (§ 4): **F1** come oggi (voce, sfida se la voce è incerta);
   **F2 «possesso»** (voce + sfida + telefono; senza telefono: sfida + chiave); **F3 «identità»**
   (voce + sfida + chiave + telefono, tutti e quattro).
3. La chiave vocale **non è solo un ripiego**: è obbligatoria in F3 (registrare o rifare una voce,
   aggiungere o cambiare chi amministra, abbinare un telefono o uno schermo personale a chi
   amministra, ripristini), perché è l'unico strato che una registrazione della voce o un clono
   costruito da audio pubblico non contengono.
4. Salvataggio: **un hash per parola**, `scrypt(HMAC-SHA256(pepper, contesto‖indice), sale)`, con
   il **pepper in `segreti.yaml`** (fuori dai backup). Detto senza giri: 5 parole da 250 sono
   ~40 bit, e chiedendone 2 per volta ogni parola si verifica da sola (8 bit): **senza il pepper un
   database rubato non dice nulla, con il pepper la chiave cade in un paio di minuti di CPU** (§ 7).
   Difende online (3 errori, blocco, ripristino solo da terminale), non da chi possiede la DGX.
5. La conferma sul telefono **non usa notifiche push** (servirebbero i server di Apple o Google,
   principio 9): la richiesta aspetta che la pagina del telefono sia aperta; «non ho il telefono»
   porta subito alla chiave (§ 6).

## 1. Modello delle minacce

Chi attacca vuole un'azione di chi amministra: un'estensione con rete o dati, una voce
registrata (la propria, per diventare «di casa»), un amministratore in più, un telefono suo
abbinato come «telefono di Dario», un'installazione, uno sblocco. Fuori dal progetto: il codice di
Calliope o la DGX compromessi con i permessi dell'utente di Calliope (lì l'attaccante ha già
tutto), e i dati non fidati nel contesto del modello (li governa la politica del 05/10).

| # | Minaccia | Voce | Sfida | Telefono | Chiave | Cosa resta |
|---|---|---|---|---|---|---|
| M1 | Persona nella stanza (ospite, familiare) che chiede a nome di Dario | ferma (non è la sua voce) | — | ferma | ferma | nulla |
| M2 | **Registrazione rifatta** della voce di Dario (messaggio vocale, video) | passa | **ferma** (parole scelte un attimo prima) | ferma | ferma | nulla |
| M3 | **Voce clonata offline** (TTS addestrato su audio pubblico o registrato di nascosto) che dice frasi preparate | passa (CAM++ non distingue un buon clone) | **ferma** se il clone non genera in tempo reale | ferma | **ferma** (il segreto non è in nessun audio) | nulla |
| M4 | **Voce clonata in tempo reale** (l'attaccante scrive le parole della sfida e il clone le dice) | passa | **passa** | **ferma** | ferma, salvo che abbia sentito la chiave (M5) | F2 senza telefono con chiave nota |
| M5 | Chi **ha sentito o registrato** Dario dire 2 parole della chiave | — | — | — | ferma 9 volte su 10 alla volta dopo (§ 7.4) | dopo più ascolti la chiave è nota: va cambiata |
| M6 | **TV, radio, video** con la voce di Dario o il nome «Calliope» | ferma o passa | ferma | ferma | ferma | nulla |
| M7 | **Ospite** con il suo telefono | ferma (livello) | — | ferma (non abbinato) | — | nulla |
| M8 | **Minore** di casa (anche con il telefono di Dario in mano) | ferma (livello e `minori.permesso`) | — | il tocco da solo non basta | — | nulla |
| M9 | **Furto del database** (`memoria.db`, `speakers.json`, un backup) | impronte rubate: non servono a parlare | — | token solo come SHA-256 | hash inutili senza pepper | con `segreti.yaml` anche la chiave (§ 7) |
| M10 | **Furto del telefono** (sbloccato o con il codice) | serve ancora la voce di Dario | serve la presenza | **passa** | **ferma** | F2 con un clone in tempo reale; revoca (§ 5.4) |
| M11 | **Schermo lasciato sbloccato** (il kiosk dello studio sul portatile) | — | — | **ferma**: F2/F3 si confermano solo dal telefono, non dagli altri schermi personali | — | nulla |
| M12 | **Satellite compromesso** (portatile con un malware): inietta audio, mostra schede finte | audio iniettato passa come M2–M4 | ferma M2/M3 | **ferma** (oggetto separato) | ferma | se è compromesso il **telefono**: come M10 |
| M13 | **Stanchezza da conferme** (richieste ripetute finché Dario tocca «Approva» per sbaglio) | — | — | tocco tenuto 1 s, al più 3 richieste in 10 min, un rifiuto blocca F2/F3 per 10 min | — | nulla di nuovo |

Due limiti onesti. (a) Contro M4 la sfida è inutile: per F2 vale il telefono, e senza telefono la
chiave (che M4 non ha, a meno di M5). (b) Contro M10 + M4 + M5 insieme (telefono rubato, clone in
tempo reale, chiave ascoltata) non c'è difesa in casa: si revoca il telefono e si cambia la chiave
da terminale.

## 2. Il telefono: come si riconosce oggi

Nell'archivio (`calliope/schermi/archivio.py`, `calliope/satellite/archivio.py`):

- uno **schermo personale** è una riga di `schermi` con `proprietario` = `UserProfile.id`; lo
  schermo che un satellite apre ha `schermi.satellite` = id del satellite (dal 05/10);
- il **telefono** è un satellite come gli altri (tabella `satelliti`), abbinato da terminale con
  `--stanza telefono --personale Dario`; nel «ciao» manda `nome: "telefono"` e si collega da
  `/telefono/ws/sessione`. **Non c'è un campo che dica «è un telefono»**: `stanza` è un nome scelto
  da chi abbina e `nome` lo dichiara il client;
- `satelliti.ruolo` (03/10) vale `"pc"` o NULL, ed è **deciso da chi abbina**. La migrazione del
  03/10 ha messo `"pc"` a tutti i satelliti già abbinati: se il telefono di Dario era già abbinato
  quella mattina, oggi ha `ruolo = 'pc'` (da controllare con `calliope satellite --elenco`).

Proposta: un valore nuovo di `ruolo`, **`"telefono"`**, deciso solo da chi abbina
(`--abbina … --telefono`, `--modifica <satellite> --telefono`), mai dal client. «Il telefono di X»
= satellite con `ruolo = 'telefono'` e `proprietario = X.id`; le conferme F2/F3 si accettano solo
da una sessione SSE dello **schermo di quel satellite** (`schermi.satellite`). Per Dario, una
volta sulla DGX:

```bash
calliope satellite --elenco                          # il telefono e lo studio, con ruolo e proprietario
calliope satellite --modifica telefono --telefono    # ruolo «telefono» (toglie «pc» se c'era)
```

Il portatile «studio» resta `ruolo = 'pc'` e personale di Dario: è il suo **schermo personale**.

## 3. Requisito: chi amministra ha telefono e schermo personale

| Stato di chi amministra | Condizione | Cosa può fare |
|---|---|---|
| **completo** | telefono (`ruolo = 'telefono'`, suo) + schermo personale + chiave vocale impostata e non bloccata | tutto, con i gradini di § 4 |
| **senza chiave** | telefono e schermo, chiave non impostata o bloccata | F1, F2 con il telefono; F3 no |
| **incompleto** | manca il telefono o lo schermo personale | F1; F2 e F3 **bloccate** (salvo l'abbinamento iniziale, § 5.1) |

Lo schermo personale serve per le schede di revisione (estensioni, permessi) e i moduli; il
telefono per la conferma. Un telefono abbinato come satellite apre anche il suo schermo personale:
**il telefono da solo soddisfa entrambi i requisiti** se Dario non vuole un secondo schermo
(decisione D2).

## 4. Quali azioni chiedono che cosa

Gradini nuovi in `politica.Classe`, campo `fattore` (oggi c'è solo `sfida: bool`):

| Gradino | Azioni (tool di oggi e futuri) | Fattori |
|---|---|---|
| **F0** | `sicuro`, `azione` di tutti; pericolose dei familiari (casa, PC) | come oggi: voce o conversazione, politica dei dati non fidati |
| **F1** | pericolose di chi amministra di oggi con `sfida=True`: `schermo_gestisci` (abbina di stanza, scollega), `rinomina_interlocutore`, `minore_gestisci` che **stringe**, `delega_lavoro` di codice, `estensioni_gestisci` disattiva / rimuovi / indietro, `conversazioni_dimentica`, approvare un'estensione **senza** rete e senza dati personali | voce sopra soglia nella frase; sfida se la voce è incerta (come oggi) |
| **F2 «possesso»** | approvare un'estensione con `rete`, `legge`, `invia` o comandi della casa; `installa_avvia`; i permessi «sì, sempre» del guardrail; riattivare un'estensione disattivata per impronta cambiata; `minore_gestisci` che **allarga** (orari, tool, estensioni); fatture (`ufficio_livello_fiscale`); le future azioni del pannello di amministrazione | voce + **sfida sempre** + **tocco sul telefono**; se il telefono non c'è o Dario dice «non ho il telefono»: sfida + **chiave** (2 parole) |
| **F3 «identità»** | `registra_utente` (voce nuova o impronta rifatta, anche la propria); aggiungere o togliere chi amministra; abbinare **a chi amministra** un telefono o uno schermo personale (`schermo_gestisci personale` verso un amministratore, il futuro abbinamento dei satelliti a voce); cambiare la chiave; sblocchi e ripristini fatti a voce | voce + sfida + **chiave** + **telefono**, tutti; nessun ripiego a voce: senza telefono, solo il terminale (salvo § 5.4) |
| **solo terminale** | ripristino della chiave bloccata o dimenticata; primo amministratore senza telefono; revoca di tutti i telefoni di tutti | `calliope passkey …`, `calliope satellite …` sulla DGX |

Per livello di chi parla:

| Livello | F0 | F1 | F2 | F3 |
|---|---|---|---|---|
| ospite | solo i suoi tool | no | no | no |
| familiare (adulto) | sì | no (non amministra) | no | no |
| minore | secondo `minori.permesso` | no | no | no |
| chi amministra, incompleto | sì | sì | **bloccata** | **bloccata** (salvo abbinamento iniziale) |
| chi amministra, senza chiave | sì | sì | solo con il telefono | **bloccata** |
| chi amministra, completo | sì | sì | sì | sì |

Insieme o in alternativa:

- **sfida + telefono** (F2 normale): la sfida prova la presenza, il tocco il possesso. Partono
  **insieme**: Calliope chiede la sfida e nello stesso momento manda la richiesta al telefono;
  l'azione parte quando arrivano entrambi (in qualunque ordine) entro la scadenza.
- **sfida + chiave** (F2 senza telefono): una frase sola, «Ripeti girasole, matita, quarantadue,
  poi dimmi la seconda e la quinta parola della tua chiave».
- **sfida + chiave + telefono** (F3): la frase sola di sopra e il tocco in parallelo.
- La chiave **non sostituisce** mai la sfida (una registrazione di una chiave detta in passato ha
  già 2 parole su 5: la sfida la rende inutile nello stesso turno) e il telefono non sostituisce la
  voce (chi tocca deve essere chi ha chiesto: la richiesta nasce solo da una frase riconosciuta).

## 5. Ciclo di vita

### 5.1 Prima installazione

Il primo utente diventa chi amministra («Primo/Prima», come oggi) ed è **incompleto**. Dopo la
registrazione della voce Calliope dice:

> «Fatto, ora riconosco la tua voce e sei tu ad amministrare Calliope. Per le cose più delicate mi
> serve anche il tuo telefono: apri sul telefono l'indirizzo che vedi nella pagina degli schermi e
> poi abbinalo dal terminale. Finché non c'è, alcune cose non le faccio.»

Abbinamento iniziale, **solo finché nessun telefono è mai stato abbinato a un amministratore**:

1. da terminale (consigliato): `calliope satellite --abbina <codice> --stanza telefono
   --personale <nome> --telefono`;
2. a voce (quando ci sarà il tool di abbinamento dei satelliti): voce + sfida, una volta sola,
   con il registro dei turni e una riga nel journal.

Poi la chiave: «Calliope, crea la mia chiave vocale» (§ 6.3), confermata dal telefono appena
abbinato. Finché manca, F2 funziona con il telefono e F3 è bloccata.

### 5.2 Amministratore esistente (Dario oggi)

Al primo avvio della versione nuova Dario è «incompleto» se il telefono ha `ruolo = 'pc'`: il
registro delle capacità dice il comando di § 2. Niente blocco a sorpresa sull'uso di tutti i
giorni: F0 e F1 restano come oggi. Le azioni F2/F3 rispondono:

> «Questo lo faccio solo con la conferma dal tuo telefono, e non hai ancora un telefono abbinato
> per le conferme. Sulla DGX: calliope satellite --modifica telefono --telefono.»

(Il comando si dice solo a chi amministra, come i passi del registro delle capacità.)

### 5.3 Secondo amministratore

Aggiungerlo è **F3 del primo** (voce + sfida + chiave + telefono di chi già amministra). Il nuovo
nasce **incompleto**: abbina il suo telefono (F3 sua: non ha ancora chiave né telefono, quindi
vale l'approvazione sul **telefono dell'altro amministratore** più la sua voce e la sfida, oppure
il terminale) e crea la sua chiave. Le richieste di uno non si confermano mai dal telefono
dell'altro, tranne questo abbinamento iniziale, che avvisa con una scheda su tutti i telefoni di
chi amministra.

### 5.4 Telefono perso, rubato o revocato

- **Revoca** subito, senza fattori (è la direzione sicura): a voce «Calliope, revoca il mio
  telefono» (voce riconosciuta nella frase, F0), o `calliope satellite --revoca telefono`.
- Dopo la revoca chi amministra è **incompleto**: F2 e F3 bloccate (F2 non ripiega sulla chiave
  in questo stato: il telefono perso è proprio il caso in cui la chiave potrebbe essere stata
  sentita da chi l'ha preso; decisione D4).
- **Telefono nuovo**: da terminale; oppure a voce con voce + sfida + chiave + **10 minuti di
  attesa** con un avviso sugli altri schermi personali e sui telefoni degli altri amministratori
  («Stanno abbinando un telefono nuovo a Dario: se non sei tu, di' "Calliope, annulla"»). È
  l'unico F3 senza telefono, e per questo ha l'attesa.
- La chiave non si cambia da sola, ma Calliope la propone dopo una revoca: «Ti consiglio di
  cambiare anche la chiave vocale.»

### 5.5 Chiave bloccata o dimenticata

Tre errori → **bloccata** finché `calliope passkey --sblocca <nome>` (o `--rifai <nome>`, che
stampa 5 parole nuove sul terminale) sulla DGX. Ripristino **solo da terminale** (decisione di
Dario): chi ha il terminale ha già i dati di Calliope.

## 6. Flussi a voce, con le frasi

Le frasi sono costanti nel codice (come `conferme.SFIDA_*`), mai scritte dal modello. `{cosa}` è
la descrizione della politica («approvare l'estensione meteo, che usa internet»).

### 6.1 F2 con il telefono

| Chi | Frase |
|---|---|
| Dario | «Calliope, approva l'estensione meteo.» |
| Calliope | «Per approvare l'estensione meteo, che usa internet, ripeti: girasole, matita, quarantadue. Poi conferma sul telefono.» (al telefono parte la richiesta) |
| Dario | «Girasole, matita, quarantadue.» |
| Calliope (tocco già arrivato) | «Fatto: ho approvato l'estensione meteo.» |
| Calliope (tocco non ancora arrivato) | «Bene. Ora tocca Approva sul telefono: apri Calliope, la richiesta è lì per un minuto.» |
| Calliope (tocco arrivato dopo) | annuncio: «Approvata dal telefono: l'estensione meteo è attiva.» |
| Calliope (scaduta) | «La conferma dal telefono non è arrivata, quindi non procedo: chiedimelo di nuovo.» |
| Calliope (rifiutata) | «Hai rifiutato dal telefono: non procedo.» (e F2/F3 bloccate 10 min) |

### 6.2 F2 senza telefono

| Chi | Frase |
|---|---|
| Dario | «Non ho il telefono.» (oppure nessun telefono collegato da più di `secondo_fattore_assenza_s`) |
| Calliope | «Allora usa la chiave vocale, quando nessuno ti sente. Ripeti: candela, vulcano, sessantuno, poi dimmi la seconda e la quinta parola della tua chiave.» |
| Dario | «Candela, vulcano, sessantuno, pinguino, faro.» |
| Calliope (giusta) | «Fatto: ho approvato l'estensione meteo.» (la richiesta sul telefono si ritira) |
| Calliope (sbagliata, 1° e 2°) | «La chiave non torna. Ripeti: … e dimmi la prima e la terza parola della chiave.» (posizioni nuove) |
| Calliope (3°) | «La chiave non torna per la terza volta, quindi l'ho bloccata. Si sblocca solo dal terminale della DGX.» |
| Calliope (parole fuori elenco) | «Non ho capito le parole della chiave. Ripetile più lentamente.» (non conta come errore, al più 2 volte) |

### 6.3 Creare o cambiare la chiave (F3; la prima volta F2 con il telefono)

| Chi | Frase |
|---|---|
| Dario | «Calliope, crea la mia chiave vocale.» |
| Calliope | «Te la mostro sul telefono, non la dico ad alta voce. Prima conferma: ripeti matita, foresta, ventotto, e tocca Approva.» |
| Calliope (dopo) | «La tua chiave è sul telefono: cinque parole, in ordine. Imparale, poi dimmele tutte e cinque, quando nessuno ti sente.» (scheda personale sul solo telefono, mai in cronologia, tolta dopo 2 minuti o alla verifica) |
| Dario | «Pinguino, faro, castagna, aquilone, veliero.» |
| Calliope (tutte capite) | «Perfetto, la chiave è salvata. Te ne chiederò due parole alla volta.» |
| Calliope (una non capita) | «Non ho capito bene "aquilone": te la cambio con un'altra parola, guarda il telefono.» |

Le parole le **sceglie Calliope** a caso (`secrets`), non la persona: è l'unico modo per avere
davvero ~40 bit. Si può chiedere un'altra serie («cambiala») al più 3 volte.

### 6.4 F3 completo

«Per registrare la voce di Giulia, ripeti: tulipano, castello, trentasei, poi dimmi la terza e la
quarta parola della tua chiave. E conferma sul telefono.»

## 7. La chiave vocale

### 7.1 Elenco e forma canonica

- Elenco chiuso di **250 parole di 3–5 sillabe** (`passkey.PAROLE`, versionato: `it-250-v1`, scelte con la misura di § 11), separato da
  `conferme.PAROLE` (le 27 della sfida): così si sa sempre quale parte della frase è sfida e quale
  chiave, e una sfida detta non rivela mai parole della chiave.
- Forma canonica = **l'indice nell'elenco** (0–249): la trascrizione si normalizza (minuscole,
  senza accenti né punteggiatura) e ogni parola si mappa alla più vicina dell'elenco solo se unica
  (SequenceMatcher ≥ 0,8 e margine ≥ 0,1 sulla seconda); come nella sfida, anche le parole spezzate
  in due. Si hasha l'indice, mai il testo trascritto.
- Ordine detto = ordine chiesto («la seconda e la quinta»): le due parole si confrontano con le
  posizioni chieste; se la frase contiene anche la sfida, la chiave è ciò che resta dopo le parole
  della sfida e il numero.

### 7.2 Salvataggio

Tabella `passkey` in `memoria.db` (versione in `meta_schema`, `persistenza.migra`):

| Campo | Contenuto |
|---|---|
| `persona` | `UserProfile.id` (chiave) |
| `formato` | 1 |
| `elenco` | `it-250-v1` e lo SHA-256 dell'elenco (un elenco cambiato invalida la chiave invece di confrontare indici sbagliati) |
| `n_parole` | 5 |
| `kdf` | `scrypt`, `n` = 2^15, `r` = 8, `p` = 1, `dklen` = 32 (`hashlib.scrypt`, libreria standard, `maxmem` 64 MiB) |
| `pepper_id` | i primi 8 caratteri esadecimali di SHA-256(pepper): dice quale pepper serve, non lo rivela |
| `sali` | 5 × 16 byte a caso, uno per posizione |
| `hash` | 5 × 32 byte: `scrypt(HMAC-SHA256(pepper, "calliope-passkey/1/" + persona + "/" + posizione + "/" + indice), sale_i)` |
| `generazione` | cresce a ogni cambio (le richieste vecchie non valgono più) |
| `errori`, `bloccata`, `ultime_posizioni` | contatore persistente, blocco, ultime 3 coppie chieste |
| `creata`, `usata` | date |

**Pepper**: 32 byte a caso in `segreti.yaml` (`passkey: pepper: "<hex>"`), creato alla prima
chiave, permessi 600 (`sicurezza.proteggi_dati`). `segreti.yaml` **non è** tra i `DATI_PICCOLI`
del gestore (`setup/linux/gestore.py`), quindi non finisce nei backup di `memoria.db`. Senza
pepper le chiavi valgono «guaste» (capacità «amministrazione» guasta, ripristino da terminale).
Confronto con `hmac.compare_digest`. Verifica di 2 posizioni: 2 scrypt, **~0,15 s** sul portatile
(misura in § 11.1), nel thread dei tool.

### 7.3 Entropia e resistenza

| | Valore |
|---|---|
| 5 parole da 250, scelte da Calliope | log2(250⁵) ≈ **39,8 bit** |
| una parola | log2(250) ≈ 8 bit |
| indovinare 2 posizioni a caso, online | 1 su 62 500 per tentativo; con 3 tentativi prima del blocco **4,8 × 10⁻⁵**, e serve anche la voce, la sfida e (F3) il telefono |
| database rubato **senza** pepper | nessuna informazione: l'HMAC con 256 bit di chiave non si inverte |
| database **e** pepper rubati | ogni posizione si verifica da sola: 5 × 250 scrypt ≈ 1 250 × 75 ms ≈ **1,5 min** su un core (la chiave intera, non solo 2 parole) |
| con un hash solo dell'intera frase (5 parole) | 2^39,8 × 75 ms ≈ 2 600 anni-core: ma allora non si possono chiedere 2 posizioni |
| un hash per **coppia** di posizioni (10 hash) | 16 bit a coppia: 65 536 × 75 ms ≈ 80 min-core a coppia, 3 coppie bastano. Non vale la complessità |

Conclusione: il segreto contro il furto è il **pepper**, non scrypt. Il progetto lo dice nel
registro delle capacità e in `prove/LEGGIMI.md`; scrypt resta per alzare il costo se il pepper esce
(minuti invece di millisecondi) e perché costa poco. Alternativa più forte (decisione D5): il pepper
non nel file ma derivato da una chiave nel TPM o nel portachiavi del sistema; sulla DGX non c'è un
TPM usato da Calliope, quindi oggi no.

### 7.4 Ascolti e registrazioni della chiave

Chiedere 2 posizioni su 5 vuol dire che chi registra **una** risposta conosce 2 parole con la loro
posizione. Calliope sceglie la coppia nuova **diversa dalle ultime 3** e con almeno una posizione
non chiesta l'ultima volta: con una registrazione la coppia chiesta dopo non è mai già nota (con la
scelta a caso sarebbe 1 su 10). Dopo 2–3 ascolti diversi (4–5 parole note) la chiave non protegge
più: per questo

- la frase dice «quando nessuno ti sente»;
- la chiave si chiede **solo** in F2 senza telefono e in F3 (rare: poche volte al mese);
- dopo `passkey_cambio_usi` usi (proposta 6) Calliope suggerisce di cambiarla (decisione D3);
- e la sfida nella stessa frase impedisce di rifare l'audio di una risposta vecchia.

### 7.5 Dove la chiave non deve finire

Come le parole della sfida, la frase con la chiave si **intercetta prima del modello** (in Brain,
accanto a `_sfida_reply`, quando c'è una richiesta di chiave in corso per quella persona) e:

| Posto | Oggi per la sfida | Per la chiave |
|---|---|---|
| storia del modello | la frase non entra | non entra; al suo posto «(conferma con la chiave)» |
| registro dei turni | solo la regola `sfida_voce` | `richiesta`/`risposta` vuote, regole `passkey_ok` / `passkey_errata` / `passkey_bloccata`, mai le posizioni |
| archivio delle conversazioni | — | il turno non si archivia |
| terminale / journal | riga «Tu: …» | riga «Tu: (chiave vocale)» (`main.in_console`) |
| audio di debug (`CALLIOPE_DEBUG_AUDIO`) | salvato | **non salvato**, né WAV né testo |
| diagnostica del telefono | — | spenta mentre la richiesta è aperta |
| `stt_correzione` (spenta) | — | mai sulla frase della chiave (andrebbe al modello) |
| satellite → server | TLS | TLS; il satellite non registra nulla |
| server Whisper (whisper.cpp) | in memoria | in memoria; niente log delle richieste (da verificare nell'unità: `-nlp`?) |

## 8. Conferma sul telefono: protocollo

1. La politica decide F2/F3 e crea una **richiesta**: `id` (128 bit, `secrets.token_urlsafe`),
   `persona`, `tool`, `argomenti` (copia), `impronta` = SHA-256 del JSON canonico di
   (persona, tool, argomenti, generazione della chiave, turno), `cosa` (la frase di § 6), `righe`
   (gli argomenti mostrati, al più 6, troncati a 80 caratteri, presi dalla stessa `cosa` della
   politica), `scade` = ora + `conferma_telefono_s` (90 s).
2. **Evento SSE `conferma`** solo alle sessioni degli schermi con `satellite` = un satellite con
   `ruolo = 'telefono'` e `proprietario = persona`. Mai agli altri schermi, mai in cronologia.
   Contenuto: `{id, cosa, righe, scade, impronta}`. Alla riapertura della pagina (`benvenuto`)
   arrivano le richieste ancora aperte.
3. La pagina mostra uno strato a tutto schermo: la frase, le righe, «Approva» (**tenuto premuto
   1 s**, contro i tocchi per sbaglio) e «Rifiuta». `POST /api/conferma` con
   `X-Calliope-Sessione`, `{id, esito, impronta}`.
4. Il server accetta solo se: sessione valida e in HTTPS; schermo di un satellite `telefono` di
   **quella** persona; `id` aperto, non scaduto, **mai usato** (si chiude al primo POST, qualunque
   esito); `impronta` uguale a quella ricalcolata **adesso** dagli argomenti dell'azione in sospeso
   (argomenti cambiati = richiesta nuova, la vecchia non vale). Altrimenti 403/409/410 senza
   dettagli.
5. Le richieste nascono **solo** da una frase con la voce di chi amministra sopra soglia (o una
   sfida superata) e dalla politica: mai dal modello, dal telefono o da uno schermo. Il telefono
   approva, non chiede.
6. Al più 3 richieste aperte o chiuse in 10 minuti per persona; oltre, «Troppe richieste di
   conferma in poco tempo: riprova tra qualche minuto.» e una scheda d'avviso sul telefono. Un
   «Rifiuta» blocca F2/F3 della persona per 10 minuti e lo segnala sul telefono.
7. **Telefono spento o pagina chiusa**: non si sa subito (iOS sospende la pagina, niente push). Se
   la persona non ha nessun telefono `telefono` → subito il ripiego (F2) o il rifiuto (F3). Se ce
   l'ha, la richiesta aspetta fino a `scade`; «non ho il telefono» (riconosciuto dal modello come
   risposta alla domanda in sospeso, poi una frase fissa) passa al ripiego. Un telefono mai visto
   da più di 30 giorni vale come assente nel registro delle capacità (avviso, non blocco).
8. Registro dei turni: `conferma_telefono_inviata`, `_approvata`, `_rifiutata`, `_scaduta`,
   `_rifiutata_server` (con il motivo in una parola), mai il contenuto.

Più avanti (fase 4 degli schermi, certificato con un nome DuckDNS): **WebAuthn** sul telefono
(Face ID o impronta: verifica dell'utente nel telefono stesso). Con un indirizzo IP non si può (il
RP ID deve essere un dominio). Toglierebbe M10 con il telefono sbloccato.

## 9. Registro delle capacità

Capacità nuova **«amministrazione»** (la 19ª), statica più dinamica (telefono visto):

| Stato | Quando | Prossimo passo (solo a chi amministra) |
|---|---|---|
| attiva | ogni amministratore è completo | — (note: «Dario: telefono, schermo studio, chiave impostata, usata 2 volte») |
| da_configurare | un amministratore incompleto o senza chiave | «Abbina il telefono di Dario per le conferme: calliope satellite --modifica telefono --telefono» / «Crea la chiave vocale: di' "crea la mia chiave vocale"» |
| guasta | pepper mancante o elenco cambiato; chiave bloccata | «La chiave di Dario è bloccata: calliope passkey --sblocca Dario» |

`calliope stato --dettagli` mostra per persona: telefono (nome, ultimo collegamento), schermo
personale, chiave (impostata, generazione, usi, bloccata). Mai hash, sali o posizioni.

## 10. Interazioni

- **Politica** (`politica.py`): `Classe.fattore` (`None`, `"sfida"`, `"possesso"`,
  `"identita"`); `sfida=True` di oggi diventa `fattore="sfida"`. Con dati non fidati di mezzo
  valgono **prima** le regole della politica (azione non chiesta, argomenti esterni), poi il
  gradino: un'estensione approvata «perché lo dice la pagina» si ferma prima di arrivare al
  telefono. `estensioni_gestisci approva` passa a F2 se il manifesto ha scope `rete`, `legge`,
  `invia` o comandi della casa (la decisione la prende il servizio, che conosce il manifesto).
- **Conferme** (`conferme.py`): `Sfida` resta; si aggiunge `Sfida.chiave` (posizioni chieste) e
  `confronta` separa le parole della sfida da quelle della chiave. `admin_confermato` non basta più
  per F2/F3: serve `secondo_fattore.soddisfatto(richiesta)`. «Una conferma per azione» (06/10)
  resta: il tocco o la chiave valgono anche come «Procedo?» del tool.
- **Minori**: un minore non ha chiave, non ha richieste di conferma, e il suo telefono non può
  avere `ruolo = 'telefono'` (il terminale rifiuta `--telefono` con `--personale` di un minore). Un
  tocco dal telefono di Dario fatto dal figlio non basta mai da solo (serve la frase di Dario).
  `minore_gestisci` che allarga è F2 (decisione D6).
- **Satelliti**: la frase può arrivare da qualunque satellite; la conferma solo dal telefono.
  Con le corsie (06/10) la richiesta è della **conversazione della persona**: se Dario chiede dal
  portatile e poi parla dal telefono, la sfida e la chiave valgono da entrambi; un altro satellite
  con un'altra persona non vede nulla.
- **Telefono come satellite**: se Dario parla **dal telefono stesso**, telefono e voce arrivano
  dallo stesso oggetto. Possesso sì (il token del telefono), ma un telefono rubato fa entrambe le
  cose: per questo F3 vuole la chiave anche lì. F2 dal telefono stesso con il telefono: va bene
  (decisione D7: oppure chiave obbligatoria quando la frase arriva dal telefono).
- **Scrivere invece di parlare**: le frasi scritte non avviano mai F2/F3 (già oggi `serve_la_voce`);
  la chiave non si scrive mai (la casella dello schermo è leggibile da chi ha lo schermo).
- **Registro delle regole** (principio 10): l'intercettazione della risposta alla chiave è un
  vincolo di sicurezza su un'azione già scelta, come la sfida; ha casi contrari nelle prove.

## 11. Piano di misura

### 11.1 Misura pilota (fatta, 06/10, solo Piper, CPU)

Uno script fuori dal repository (congelamento), sullo schema di `prove/misura_sfida.py`, da rifare come `prove/misura_passkey.py` alla
realizzazione; elenco e risultati nell'appendice: **158 parole candidate** (concrete, 2–5 sillabe, niente parole della sfida, di
uscita, del nome, della casa o dei comandi), 10 voci italiane di Piper, frasi da 5 parole separate
da virgole, faster-whisper large-v3-turbo su CPU (int8) con la configurazione predefinita
(beam 5, hotwords «Calliope»), mappatura all'elenco come in § 7.1.

Interrotta dopo 5 voci su 10 (tetto di 30 minuti del processo in background: ~5 min per voce
su CPU, ~9 s a frase con la sintesi): aurora, dii, giorgio, leonardo, miro; mancano paola, serena
e riccardo, le migliori nella misura della sfida del 04/10. 160 frasi, 790 parole.

| Misura | Valore |
|---|---|
| parole trascritte esatte | 63,0 % |
| parole riconosciute dopo la mappatura all'elenco | **81,6 %** |
| per voce | miro 145/158, dii 143, giorgio 137, aurora 122, leonardo 98 |
| per sillabe | 2 sillabe **67 %** (100 viste), 3 sillabe 82 %, 4 sillabe 85 %, 5 o più **92 %** |
| per posizione nella frase | prima parola **74 %**, le altre 81–87 % |
| parole mai mancate su 5 voci | **61 su 158** (39 %) |
| parole comparse al posto di altre | 3 (polpo, tamburo, riccio) |
| coppie simili (SequenceMatcher ≥ 0,7) nell'elenco | 38 (specchio/secchio 0,93, fenicottero/elicottero 0,86…) |
| durata di una frase da 5 parole | 5,7 s (mediana, Piper) |
| `hashlib.scrypt`, r = 8, p = 1, sul portatile | N = 2^14 41 ms, **2^15 76 ms**, 2^16 149 ms |

Cosa se ne ricava:

- **Solo parole di 3 o più sillabe**, meglio 4–5; via le due sillabe (gufo, orso, tigre, faro,
  razzo, prato: le più mancate).
- **Mai una parola della chiave in testa alla frase**: nella risposta vengono dopo la sfida
  («…quarantadue, pinguino, aquilone»), che fa da attacco.
- **Un elenco più largo**: a questo tasso servono ~600–700 candidate per tenerne 250 a zero errori
  (meglio con le voci vere che con Piper: Piper medium è più difficile della voce di una persona, e
  la sfida del 04/10 con le stesse voci dava il 98 % su quelle pulite). Se 250 non si raggiungono:
  200 parole (38,2 bit con 5) o 6 parole da 150 (43 bit) (decisione D8).
- **Niente coppie simili**: una parola sola per ogni coppia sopra 0,7, anche contro le 27 della
  sfida.

### 11.2 Misure da fare prima di scegliere l'elenco

| Misura | Come | Soglia |
|---|---|---|
| Elenco da 250 | ~400 candidate × 10 voci Piper × 3 giri; tenute quelle mai mancate né comparse al posto di altre | ≥ 250 parole a 0 errori |
| **Voce vera di Dario** | 80 frasi da 5 parole lette dal portatile (C920) e dal telefono, `CALLIOPE_DEBUG_AUDIO`; Whisper della DGX (whisper.cpp, senza hotwords) e faster-whisper | parola riconosciuta ≥ 99 %; tolte quelle mancate |
| Omofoni e vicine | coppie con SequenceMatcher ≥ 0,7 nell'elenco e contro le 27 della sfida | 0 coppie |
| Falsi rifiuti | 200 risposte simulate (sfida + 2 parole) con le voci e il confronto vero | F2 senza telefono ≤ 3 %, F3 ≤ 5 % |
| Falsi accetti | risposte con 2 parole sbagliate dall'elenco | 0 |
| Latenza | dalla fine della frase all'esito: STT + mappatura + 2 scrypt sulla DGX | ≤ 0,5 s oltre allo STT |
| Telefono | tempo dal comando al tocco, 10 volte (pagina aperta / telefono in tasca) | — (si misura, nessuna soglia) |

### 11.3 Costo stimato per azione

| Gradino | Turni | Tempo (stima) | Falsi rifiuti (stima) |
|---|---|---|---|
| F1 oggi (voce sicura) | 1 | 0 s in più | 0 % sopra 3 s di voce |
| F2 con telefono | 2 (richiesta, sfida) + tocco in parallelo | +8–15 s (sbloccare il telefono e aprire la pagina) | sfida: 2 % su voce pulita (misura del 04/10), il tocco ~0 |
| F2 con chiave | 2 | +5–7 s; verifica 2 × 76 ms di scrypt | Piper, parole scelte: ~3 % a parola, quindi ~6 % per la chiave e ~20 % con la sfida (80 % di sfide passate il 04/10); voce pulita: sfida 2 %, chiave da misurare (stima 5–8 % in tutto). Una ripetizione con le parole fuori elenco non conta come errore |
| F3 | 2 + tocco | +10–15 s | come F2 con la chiave (il tocco non aggiunge rifiuti) |

Sono azioni rare (poche al mese): il costo è accettabile se i falsi rifiuti restano sotto il 5 %,
perché ogni rifiuto rifà tutto e il terzo errore della chiave blocca.

## 12. Cosa cambia nei file (stima)

| File | Cosa | Righe |
|---|---|---|
| `calliope/passkey.py` (nuovo) | elenco, mappatura, generazione, scrypt+HMAC, tabella, blocco, scelta delle posizioni, frasi | ~320 |
| `calliope/secondo_fattore.py` (nuovo) | stato di chi amministra (completo / senza chiave / incompleto), richieste di conferma, impronta, scadenze, limiti, ripiego | ~350 |
| `calliope/politica.py` | `Classe.fattore`, tabella, chiamata a `secondo_fattore` in `decidi` | +60 |
| `calliope/conferme.py` | sfida con le posizioni della chiave, `confronta` separato | +70 |
| `calliope/brain.py` | intercettazione della risposta (accanto a `_sfida_reply`), storia senza la frase | +90 |
| `calliope/ciclo.py` | niente audio di debug, console, archivio delle conversazioni, `stt_correzione` sulla frase della chiave | +40 |
| `calliope/schermi/hub.py`, `server.py`, `archivio.py` | evento `conferma`, `POST /api/conferma`, ruolo «telefono» | +170 |
| `calliope/satellite/__main__.py`, `archivio.py`, `setup/linux/gestore.py` | `--telefono`, `calliope passkey --crea/--sblocca/--rifai/--stato` | +160 |
| `calliope/schermi/pagina/schermo.js`, `telefono/telefono.js`, CSS | strato di conferma, tenuta 1 s, scheda della chiave | +180 |
| `calliope/capacita.py` | capacità «amministrazione» | +70 |
| `calliope/tools/` (`stato.py` o `chiave.py`) | `chiave_vocale` (crea, cambia), revoca del telefono | +130 |
| `calliope/estensioni/servizio.py` | gradino dell'approvazione dal manifesto | +30 |
| `calliope/config.py` | `conferma_telefono_s`, `passkey_*`, `secondo_fattore_obbligatorio` | +40 |
| **Codice** | | **~1 700** |
| prove | sotto | ~1 300 |

## 13. Prove da scrivere

**A secco** (livello 2, legate a `politica`, `conferme`, `schermi`, `passkey`):

- `prova_passkey.py`: generazione (5 indici distinti, `secrets`), mappatura (spezzate, accenti,
  margine), hash e verifica, pepper mancante, elenco cambiato, blocco al terzo errore e
  persistenza dopo un riavvio, parole fuori elenco che non contano, scelta delle posizioni (mai
  una coppia delle ultime 3), sblocco solo da terminale.
- `prova_secondo_fattore.py`: tabella di § 4 per ogni livello e stato; F2 con tocco prima o dopo
  la sfida; ripiego; F3 che rifiuta senza telefono; prima installazione; revoca; secondo
  amministratore; minore.
- `prova_conferma_telefono.py`: il POST con la sessione di un altro schermo, di uno schermo
  personale non telefono, di un telefono di un'altra persona, scaduto, due volte, con
  l'impronta vecchia dopo un cambio di argomenti, in http in rete, oltre il limite; l'evento solo
  al telefono giusto.
- `prova_chiave_riservata.py`: la frase della chiave non compare in storia, registro dei turni,
  archivio delle conversazioni, console, audio di debug (con `CALLIOPE_DEBUG_AUDIO` acceso).
- In `prova_telefono_pagina.py` (Edge headless): lo strato, la tenuta di 1 s, «Rifiuta».

**D'attacco** (`prova_secondo_fattore_attacchi.py`, banco come quelli della politica):
registrazione rifatta di una risposta vecchia (sfida + chiave), risposta con le parole della
sfida vecchia, chiave detta dal modello (dato non fidato che contiene «la seconda parola è…»),
foto o allegato con la chiave scritta, frase scritta dallo schermo, «sì» breve, zona grigia,
ospite e familiare che chiedono F2, satellite che manda un `conferma` finto via WebSocket, pagina
che inventa un `id`, mille POST in un minuto, telefono revocato con la sessione ancora aperta,
minore con il telefono di Dario. Obiettivo: **0 azioni eseguite**.

## 14. Rischi residui

1. **Pepper e database insieme** (DGX compromessa o copia intera della cartella dati): la chiave
   cade in minuti. Accettato: chi ha quei file ha già Calliope.
2. **Chiave ascoltata più volte** (§ 7.4): si consuma; serve cambiarla.
3. **Telefono rubato e sbloccato + clone in tempo reale**: F2 passa. Mitigazione: revoca subito,
   WebAuthn più avanti.
4. **Nessun push**: la conferma dipende dall'aprire la pagina; su iOS si perde tempo.
5. **Più frizione** per le azioni rare: se i falsi rifiuti superano il 5 % Dario smetterà di
   usarle o chiederà di spegnere il secondo fattore (`secondo_fattore_obbligatorio: false` va
   tenuto possibile solo da `calliope.locale.yaml`, con un avviso a ogni avvio).
6. **Accessibilità**: chi non vede bene il telefono o non può tenerlo premuto; chi balbetta con la
   chiave. Da rivedere con un secondo amministratore vero.
7. La voce resta il fattore per F0/F1: questo progetto non cambia l'uso di tutti i giorni.

## 15. Fasi dopo il congelamento

| Fase | Contenuto | Dipende da |
|---|---|---|
| 1 | Misure di § 11.2 con la voce di Dario; elenco `it-250-v1` congelato | Dario: 15 minuti di lettura |
| 2 | Ruolo «telefono», capacità «amministrazione», stato di chi amministra (solo lettura: dice, non blocca) | — |
| 3 | Conferma sul telefono (F2), prove a secco e d'attacco | 2 |
| 4 | Chiave vocale (creazione sul telefono, ripiego F2, terminale) | 1, 3 |
| 5 | F3 e blocco reale dei «incompleti» (`secondo_fattore_obbligatorio: true`) | 4, una settimana d'uso di 3–4 |
| 6 | WebAuthn sul telefono | certificato con nome (fase 4 degli schermi) |

## 16. Decisioni per Dario

| # | Domanda | Proposta |
|---|---|---|
| D1 | Il gradino di ogni azione (§ 4), in particolare `installa_avvia` in F2 e la delega del codice in F1 | come in tabella |
| D2 | Il telefono basta anche come schermo personale, o serve un secondo schermo? | basta il telefono |
| D3 | Cambio della chiave dopo quanti usi | suggerito dopo 6, mai imposto |
| D4 | Dopo la revoca del telefono, F2 con la sola chiave? | no, finché non c'è un telefono nuovo |
| D5 | Pepper in `segreti.yaml` o altrove | `segreti.yaml` ora |
| D6 | `minore_gestisci` che allarga in F2 (telefono) | sì |
| D7 | Con la frase detta **dal telefono stesso**, F2 vuole anche la chiave? | no per F2, sì per F3 (già così) |
| D8 | Lunghezza della chiave e posizioni chieste: 5 e 2, oppure 6 e 2 (~48 bit, più faticosa) | 5 e 2 |
| D9 | Abbinamento iniziale del telefono anche a voce (con sfida), o solo da terminale | solo terminale finché non c'è il tool dei satelliti a voce |

## Appendice: le candidate della misura pilota

158 candidate (in grassetto le 61 mai mancate né scambiate sulle 5 voci; le altre, se non sono
di 2 sillabe, si possono riprovare con le voci vere):

**leone**, tigre, zebra, orso, lupo, **volpe**, aquila, gabbiano, pappagallo, **coccodrillo**,
tartaruga, canguro, cammello, lumaca, **formica**, **balena**, **medusa**, polpo, **gambero**,
pavone, gufo, civetta, criceto, **coniglio**, asino, **pecora**, capra, gallina, anatra, cigno,
airone, fenicottero, **ippopotamo**, **rinoceronte**, scimmia, panda, koala, lontra, **castoro**,
riccio, **talpa**, ragno, vespa, cicala, grillo, limone, **arancia**, **banana**, ananas, lampone,
mirtillo, carciofo, zucchina, melanzana, **peperone**, **cipolla**, patata, fagiolo, **castagna**,
nocciola, mandorla, pistacchio, **oliva**, **formaggio**, **mozzarella**, **prosciutto**,
**salame**, **cioccolato**, caramella, focaccia, pagnotta, panino, minestra, **risotto**,
**lasagna**, polenta, **frittata**, **marmellata**, miele, forbici, **martello**, **cacciavite**,
lampada, poltrona, **divano**, armadio, **cassetto**, specchio, **tappeto**, coperta, lenzuolo,
bottiglia, bicchiere, forchetta, **cucchiaio**, **coltello**, pentola, **padella**, teiera,
scopa, secchio, zaino, **cappello**, sciarpa, guanto, stivale, ciabatta, cravatta, **bottone**,
**gomitolo**, bussola, **telescopio**, **microscopio**, **binocolo**, chitarra, **violino**,
tamburo, **trombone**, **flauto**, campana, **fischietto**, **palloncino**, aquilone, trottola,
altalena, montagna, **collina**, **pianura**, **deserto**, ghiacciaio, cascata, isola,
**spiaggia**, **scoglio**, grotta, prato, giardino, **fontana**, faro, mulino, fattoria,
**soffitta**, **campanile**, **bicicletta**, monopattino, **motorino**, autobus, camion,
**trattore**, veliero, **sottomarino**, **elicottero**, razzo, nuvola, fulmine, tempesta, pianeta,
**cometa**.

Nota: tra le 61 restano coppie simili (coniglio/scoglio, castagna/lasagna, collina/cipolla,
elicottero/sottomarino): la scelta finale toglie una parola per coppia.
