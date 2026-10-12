# Roadmap

*Nata il 06/10/2026 dalla sezione «Roadmap» di CLAUDE.md (proposta P7 di
[`ricerche/2026-10-06-analisi-complessiva.md`](ricerche/2026-10-06-analisi-complessiva.md)).
In alto lo stato e i prossimi passi; poi le proposte delle analisi, ciò che resta da fare per
area e, in fondo, la roadmap com'era, con le voci fatte segnate. Nessuna data promessa.*

## Stato (12/10/2026)

- **Le 41 domande del 12/10 hanno una risposta.** Tre revisioni di prontezza hanno letto la
  roadmap voce per voce; le scelte che valgono per più aree sono nella decisione
  [0028](decisioni/0028-decisioni-roadmap-12-10.md) (dati degli adulti per 60 giorni, piano unico
  della memoria, taglia ridotta da 8 GB come vincolo, posizione della DGX che non conta, musica sì
  e allarme senza data); le altre sono nella coda qui sotto, voce per voce.
- **Registro degli eventi** in ombra sulla DGX dall'11/10 (passi 0–3 della decisione
  [0027](decisioni/0027-conversazione-come-registro-di-eventi.md)); `eventi: attivo` si accende
  solo con i criteri di E1. **Macchina a stati**, passo 1 in ombra dal 10/10.
- **Latenza**: chiusa come lavoro il 09/10 (prima frase mediana 1,28 s), resta l'avviso di
  `calliope stato --turni` come sentinella ([contesto-conversazione](aree/contesto-conversazione.md)).
- **Politica per valore** accesa dal 09/10 sera; la fase 5 (giudice sui compiti) non si fa ora (S8).
- Trascrizione: confronto A / B / B2 / C chiuso il 07/10, si resta su A (correzione spenta)
  ([`aree/stt-tts.md`](aree/stt-tts.md)).

### Fatto dal 10/10 al 12/10

Dettagli in [`../CHANGELOG.md`](../CHANGELOG.md) e nei documenti d'area.

- **Stato del dialogo**: passo 0 (i dieci stati a rischio con una prova ciascuno), passo 1 della
  macchina a stati in ombra (`proposta_rispondi`, corsia veloce dei «sì» e «no» detti per intero)
  ([voce-e-regole](aree/voce-e-regole.md)).
- **Registro degli eventi**, passi 0–3: un registro per persona, uscita unica verso la voce,
  contesto dalla proiezione con `eventi: attivo` (acceso solo a mano)
  ([contesto-conversazione](aree/contesto-conversazione.md)).
- **Satelliti**: analisi del 10/10, i satelliti pronti parlano l'API di ESPHome e Calliope parlerà
  loro direttamente (decisione [0026](decisioni/0026-satelliti-esphome-senza-home-assistant.md)).
- **Forme chiuse storpiate da Whisper** («Annullahi», «Chiudin»…) riconosciute; frase al tetto di
  120 s unita al seguito.
- **Giochi**: modalità gioco a tutta la finestra con il pallino della voce e la variante collaudo;
  comandi a voce dichiarati dal gioco, senza il modello e senza il nome mentre aspetta una mossa
  ([giochi](aree/giochi.md)).
- **Modalità sviluppo**: collaudo di un gioco in prova sullo schermo, agente guidato (ogni
  controllo che boccia dice file, riga ed errore; scheletri per tipo), revisione onesta requisito
  per requisito con le tappe per le richieste ricche, e il 12/10 la **voce onesta** (vedi sotto)
  ([agenti-estensioni](aree/agenti-estensioni.md)).

### Fatto dal 07/10 al 09/10 (storico)

- **Sicurezza per valore**, fasi 1–3 (attrito misurato, memoria dell'intento attiva, matrice per
  valore ed effetto in ombra); un «no» chiude la proposta (09/10); fase 4 accesa e estensioni
  che leggono soltanto come letture (09/10 sera)
  ([sicurezza-politica](aree/sicurezza-politica.md)).
- **Modalità sviluppo** per estensioni e programmi, versione 2 e giri 3–6 dai casi veri,
  confronto dei collaudi, ricollaudo alla consegna, sonde verso i soli host noti; vista dello
  sviluppo sugli schermi ([agenti-estensioni](aree/agenti-estensioni.md),
  [schermi-telefono](aree/schermi-telefono.md)).
- **Modulo studio, primo passo**: esercizi generati e corretti dal programma, matematica e
  italiano ([minori](aree/minori.md)); minori: segnali di pericolo poco chiari a due cancelli.
- **Taratura della macchina**, fasi 0–2: inventario, catalogo, `calliope stato --piano` in sola
  lettura ([capacita-installazioni](aree/capacita-installazioni.md)); voce: prima frase a pezzi,
  taratura di Piper, Piper sulla GPU.
- **Conversazioni**: ricerca cronologica, continuità per le frasi cortissime, cronologia delle
  schede per persona e scheda «Conversazione»; cassetto dei file per persona.
- **Parole incerte**, F0 (misura) e F1 («forse intendevi…?» dopo un esito vuoto)
  ([stt-tts](aree/stt-tts.md)).
- **Modalità compagnia**, F0 e F1 accese (più voci vicino a un satellite: nome a ogni frase con
  una voce sconosciuta, niente frase breve); F2 («rivolta a Calliope?») in ombra.
- Casa: il dispositivo cercato per nome quando Home Assistant non lo trova ([casa](aree/casa.md)).

## Prossimi passi (coda del 12/10)

Coda ordinata secondo le risposte di chi amministra del 12/10. Per ogni voce: la sigla della
domanda, il giudizio di prontezza delle revisioni del 12/10 (**pronta**: si può partire;
**quasi**: manca un dato, una soglia o una scelta piccola; **da approfondire**: serve prima un
progetto o una rilettura) e la dipendenza principale. Nessuna data promessa. Due regole valgono
per tutte: prima di scrivere codice si rileggono le ricerche nate prima delle scelte di fondo
(secondo fattore, musica, mappe, porta delle estensioni, immagini: T6); ogni voce dice come si
comporta nella taglia ridotta da 8 GB (V7, E11).

### 0. Trasversali (decisione [0028](decisioni/0028-decisioni-roadmap-12-10.md))

1. **Conservazione dei dati** (T1): turni e audio dei soli adulti in privato per 60 giorni, minori
   e ospiti mai, un comando per svuotare tutto. **Fatta il 12/10** (ramo `conserva-metrica`,
   `calliope/conserva.py`): eventi degli adulti 60 giorni, voce in μ-law con il consenso (chi
   amministra sì finché non dice no), `calliope conserva --svuota [--persona]` e a voce per chi
   amministra; nel profilo ridotto c'è uguale (niente GPU). Resta da decidere l'archivio delle
   conversazioni di minori e ospiti ([contesto-conversazione](aree/contesto-conversazione.md)).
2. **Piano unico della memoria della DGX** (T4): un budget scritto in `calliope stato --piano`
   prima di ogni modello nuovo. *Quasi* · dipende da: una misura della memoria libera in una
   giornata tipica.
3. **Taglia ridotta da 8 GB** (V7, E11): da progettare davvero (prima era una riga «non
   definita»): cosa c'è, cosa c'è in forma minore e cosa manca su un PC con 8 GB di VRAM, quali
   modelli, reti e regole tarate per profilo. Assorbe le fasi 3–6 della taratura della macchina
   (prova breve, `taratura.json`, campi «auto», adattamento) e le sei scelte aperte della
   ricerca del 07/10. *Da approfondire* · dipende da: le misure del § 7.2 della
   [taratura](ricerche/2026-10-07-taratura-macchina.md) (guardiano piccolo e Whisper sulla CPU).

### 1. Modalità sviluppo (lavori del 12/10)

Dall'analisi del 12/10 sui log veri e sul codice: le modifiche finivano male nella specifica, la
voce raccontava male gli esiti, i comandi del flusso si perdevano.

1. **La specifica dai requisiti**: a ogni modifica la specifica si riscrive intera e i requisiti
   si rifanno da lì, invece di accodare «Con questa modifica: …». *In corso.*
2. ~~**Voce onesta**~~ *[fatta il 12/10]*: esito vero del collaudo e dell'agente, conteggio per
   tipo, revisione dal testo del tool, meno parole e meno conferme
   ([agenti-estensioni](aree/agenti-estensioni.md)).
3. ~~**Comandi del flusso e ripresa**~~ *[fatta il 12/10, ramo `flusso-ripresa`]*: «chiudi tutti
   gli sviluppi» con un solo sì, nessuna azione che non si disfa da una storpiatura, «ricominciamo»
   che sospende lo sviluppo aperto, la modifica che ferma il lavoro solo al «sì» e «lascia com'era»
   (A4), i file dei giri fermi per «rifallo» e la tappa messa da parte (A5), la ripresa in una
   domanda, il programma chiuso che si riapre (M7)
   ([agenti-estensioni](aree/agenti-estensioni.md)).
4. **Macchina a stati dei giochi** fornita da Calliope: fasi fisse (preparazione, turno, esito,
   fine) con una fase libera come scappatoia, pagine a schermo fisso ridisegnabili, comandi a voce
   per fase anche con un parametro («porta tre», limitato al dominio dichiarato), l'agente che
   scrive solo dati, logica pura e disegno. **Prima un progetto scritto.** *Da approfondire* ·
   dipende da: il progetto (rigidità, una sola fonte dello stato, lo slot che allarga la regola
   deterministica, compatibilità dei giochi già approvati).

### 2. Registro degli eventi e dialogo (E1–E11)

1. **Accendere `eventi: attivo`** (E1): dopo almeno 7 giorni d'ombra (non prima del 18/10) e almeno
   200 turni, zero differenze nel parlato, e la guardia sui riletti scritta prima. *Quasi* ·
   dipende da: i dati d'ombra sulla DGX e la guardia dei riletti.
2. **«Dimentica» chiude anche la conversazione in corso** (E2). *Pronta* · dipende da: niente
   (confermato il 12/10).
3. **Passo 4 del registro: le domande come eventi** (E3), con `attivo` già acceso; 2–3 giorni
   (circa 170 domande in 35 moduli). *Quasi* · dipende da: E1.
4. **Spezzare `Brain._reply`** (E4, era Q14) subito dopo il passo 4, fermando per qualche giorno
   gli altri lavori su `brain.py`. *Quasi* · dipende da: E3.
5. **Macchina a stati, passo 2, in due** (E5): prima il consenso unico, poi la tabella dei permessi
   ([0023](decisioni/0023-tabella-dichiarativa-dei-permessi.md)) generata da quelle di oggi, in sola
   lettura e in ombra; una sola soglia: una settimana d'ombra senza esecuzioni che la politica di
   oggi avrebbe fermato. Poi i passi 3, 5, 4, 7, 8. *Quasi* (consenso unico), *da approfondire*
   (tabella) · dipende da: E1 ed E3.
6. **Un «sì» breve per le azioni importanti** (E6): non si cambia ora; si misura in ombra e si
   decide con i numeri. *Pronta* (la misura) · dipende da: niente.
7. **La scelta dei tool come metrica e banco con le frasi vere**: la metrica in `calliope stato
   --turni` subito; il banco con le etichette di E8 (le correzioni fatte da chi amministra nella
   conversazione valgono come etichetta, il resto lo rivede l'agente a campione e chi amministra
   vede solo i casi dubbi) ([`ricerche/2026-10-10-scelta-dei-tool.md`](ricerche/2026-10-10-scelta-dei-tool.md)).
   *Pronta* (metrica), *da approfondire* (banco) · dipende da: la conservazione dei dati (0.1) e
   un estrattore dei casi. **Metrica fatta il 12/10** (`calliope/scelta_tool.py`, con gli eventi
   `dati_del_turno` e `scheda_mandata` scritti per il banco); resta il banco.
8. **Rinomina degli altri tool** (E7): la regola dei nomi dell'08/10 non è più vincolante, decide
   il banco; la rinomina aspetta i dati. *Da approfondire* · dipende da: il banco (2.7).
9. **Modalità configurazione guidata dalla voce** e pannello con le azioni (E9): Primo/a è chi ha
   installato Calliope; allargare un permesso richiede la conferma dal telefono, non la sola voce
   ([`ricerche/2026-10-10-macchina-stati.md`](ricerche/2026-10-10-macchina-stati.md) § 11).
   *Da approfondire* · dipende da: il secondo fattore (4.7) e la tabella dei permessi (2.5).
10. **Ridurre la configurazione** (E10, era Q12): un inventario una tantum dei campi mai cambiati;
    quali diventano costanti lo decide chi amministra, perché tocca la personalizzazione; nessuna
    regola «un campo nuovo ne toglie uno». *Pronta* (l'inventario) · dipende da: la scelta di chi
    amministra sull'elenco.
11. **Reti mai scattate spente nel modello da 26B** (E11, era Q13), dal 20/10, con un rapporto degli
    scatti per rete e per profilo prima di toccarle; le reti restano tarate per profilo e non si
    spengono nella taglia ridotta. *Quasi* · dipende da: lo script del rapporto e la data.

### 3. Voce, casa, notizie (V1–V11)

1. **Satelliti ESPHome** (decisione [0026](decisioni/0026-satelliti-esphome-senza-home-assistant.md)):
   il Voice PE non c'è ancora (V1): adattatore provato con un dispositivo finto; la prova vera quando
   arriva, senza data. «Okay Nabu» va bene solo in ufficio e per la prova, finché non c'è il
   firmware nostro (V2) ([`ricerche/2026-10-10-wyoming.md`](ricerche/2026-10-10-wyoming.md)).
   *Pronta* (passi a secco) · dipende da: il dispositivo finto; il dispositivo vero per i passi 3–7.
2. **Frasi pronte meno monotone**, fasi 0–1 (V3): le varianti le scrive un agente, chi amministra
   ne rilegge un campione di 30 prima dell'accensione; obiettivo sotto 8 ripetizioni ogni 100
   ([`ricerche/2026-10-08-frasi-pronte.md`](ricerche/2026-10-08-frasi-pronte.md)). *Pronta* ·
   dipende da: niente (l'id della frase pronta passa dall'uscita unica). **Fatte il 12/10 le fasi
   0–1, in ombra** (ramo `frasi-pronte`, `calliope/frasi.py`): campo `pronte` nel registro dei
   turni dall'uscita unica, ripetizioni ogni 100 in `calliope stato --turni` con la stima delle
   varianti; catalogo di 10 frasi (lavori, estensione attiva, sviluppo, cortesia) per tono e con
   la forma breve; nel profilo ridotto uguale. Resta: chi amministra rilegge il campione
   (`python -m calliope.frasi --campione --file campione.md`) e accende `frasi_varianti: attivo`;
   poi annunci di fine lavoro, ripieghi e la cornice della politica (fase 2).
3. **Compagnia F2** (V5): si rilegge l'ombra; se regge, il giudizio «rivolta a Calliope?»
   sostituisce il nome a ogni frase solo quando tutte le voci vicine sono riconosciute
   ([`ricerche/2026-10-09-piu-persone.md`](ricerche/2026-10-09-piu-persone.md)). *Quasi* · dipende
   da: la lettura dell'ombra.
4. **Parole incerte F2** (V6): se la persona corregge una parola dopo che l'azione è già stata
   fatta, Calliope propone di annullarla e rifarla con la parola giusta; F3 (dizionario delle
   correzioni) dopo un mese di F1 e F2
   ([`ricerche/2026-10-08-parole-incerte.md`](ricerche/2026-10-08-parole-incerte.md)). *Quasi*
   (F2), *da approfondire* (F3) · dipende da: le soglie di F0 tarate sulla voce vera.
5. **Notizie dai feed RSS** (V4): prima una ricerca breve con 10–15 feed veri (copertura contro
   SearXNG, condizioni d'uso); poi lo scarico ogni 2 ore, solo se negli ultimi 7 giorni qualcuno
   ha chiesto notizie (decisione [0024](decisioni/0024-niente-internet-se-non-serve.md)).
   Ricerca fatta il 12/10 ([`ricerche/2026-10-12-notizie-rss.md`](ricerche/2026-10-12-notizie-rss.md)):
   15 risposte su 22 dall'indice (4 in parte), ricerca 0,04 ms, libreria standard, fonte dentro
   `web_cerca`. *Quasi* · dipende da: le 5 domande aperte della ricerca (testate, minori).
6. **Musica** (T2, V8): requisito confermato; Music Assistant in un container apposta, da mettere
   dove serve con la posizione in configurazione; non aspetta la DGX in casa. *Da approfondire* ·
   dipende da: la rilettura della [ricerca del 21/09](ricerche/2026-09-21-musica-e-hardware-audio.md)
   (nata per un server Windows e i satelliti di Home Assistant) e chi suona sullo stesso
   dispositivo della voce.
7. **Interfono e conversazione di stanza** (V10): quando si vuole, con i satelliti che ci sono
   (telefoni, tablet, PC), senza aspettare ESPHome; più persone nella stessa conversazione (la
   compagnia oggi le distingue, non le unisce). *Da approfondire* · dipende da: un progetto su
   privacy e permessi (chi chiama chi, ospiti, minori).
8. **Mappe e luoghi** (V11): le coordinate di casa solo nel file locale e mai inviate fuori;
   percorsi calcolati offline con la DGX come server (fasi 2–3 di
   [`ricerche/2026-10-01-mappe-e-schermi.md`](ricerche/2026-10-01-mappe-e-schermi.md)). *Da
   approfondire* · dipende da: la rilettura della ricerca, scritta per Windows (Valhalla ora ha i
   wheel per Linux aarch64).
9. **Satellite di stanza su Raspberry senza PC**: resta in roadmap come satellite di stanza (il
   nostro satellite su un Raspberry a 64 bit, oppure `linux-voice-assistant` attraverso
   l'adattatore ESPHome). *Da approfondire* · dipende da: l'adattatore ESPHome (3.1) e la scelta
   dell'hardware audio.
10. **Allarme** (T2, V9): senza data. Inserire a voce più avanti, disinserire mai; oggi sola lettura.

### 4. Studio, immagini, sicurezza, estensioni (S1–S13)

1. **Materie calcolabili** (S1): logica, fisica e chimica con i numeri, con lo stesso schema della
   matematica ([`ricerche/2026-10-08-esercizi.md`](ricerche/2026-10-08-esercizi.md)). **Fatta il
   12/10** (ramo `materie-calcolabili`): logica (sequenze, insiemi, vero o falso), fisica
   (velocità, densità, forze e lavoro), chimica (massa molare, moli, bilanciamento), ognuna col
   ricalcolo indipendente; le unità a voce per esteso e lette dalle risposte di Whisper
   (`calliope/unita.py`), i simboli dopo un numero detti per esteso in ogni frase; nel profilo
   ridotto c'è uguale (solo codice, il 4B misurato). Resta la prova d'uso con un ragazzo
   ([minori](aree/minori.md)).
2. **Grammatica oltre il pilota** con il secondo parere di un modello diverso da quello della voce,
   il modello dell'agente (S2). *Quasi* · dipende da: il piano della memoria (0.2).
3. **Storia e scienze** (S3): i testi solo dalla biblioteca (Vikidia e Wikibooks da scaricare) e
   anche da **scansioni di libri**, che vanno salvate; mai testo libero del modello; domande
   generate e controllate dal programma. *Da approfondire* · dipende da: le fonti nella biblioteca
   e dove si salvano le scansioni (archivio dei documenti di casa).
4. **Simulazione d'interrogazione** (S4): prima un progetto. Contenuti dati dal ragazzo o dal libro
   fotografato; giudizio a parole senza voto numerico; l'audio non si salva. *Da approfondire* ·
   dipende da: il progetto (anche un ascolto lungo senza nome, come nei giochi).
5. **Riscontro emotivo dalla voce** (S5): rimandato a dopo l'interrogazione; resta tra le cose in
   valutazione.
6. **Immagini con FLUX.2 [klein] 4B** (S6): lo scarico di 40–80 GB e la misura solo quando il piano
   della memoria libera circa 16 GB stabili
   ([`ricerche/2026-10-06-generazione-immagini.md`](ricerche/2026-10-06-generazione-immagini.md)).
   *Quasi* · dipende da: il piano della memoria (0.2).
7. **Secondo fattore per chi amministra** (S7): si parte dalla conferma sul telefono per le azioni
   importanti; la chiave vocale dopo
   ([`ricerche/2026-10-06-secondo-fattore.md`](ricerche/2026-10-06-secondo-fattore.md)). *Quasi* ·
   dipende da: il progetto riletto e aggiornato (classi d'effetto E0–E4, tool rinominati, punto
   d'aggancio nella macchina a stati).
8. **Estensioni a orario** (S9): girano a nome di chi le ha create, con i suoi permessi del
   momento; il risultato va solo a lui; le pause dei minori valgono. *Quasi* · dipende da: un
   progetto breve (dove va il risultato, di notte, arbitro della GPU).
9. **Messaggi verso l'esterno dalle estensioni** (S10): nessuno per ora; più avanti solo notifiche
   alla web app sul telefono di casa.
10. **Node/JavaScript** come linguaggio dei programmi in diretta, sullo schema del C#. *Pronta* ·
    dipende da: i limiti dell'immagine (npm senza rete).
11. **Documenti degli agenti al satellite**: fatto in gran parte dal 07/10 (il risultato va al
    portatile con «Lo apro?»); restano il telefono e più satelliti personali della stessa persona.
    *Quasi*.
12. **Isolamento vero della sandbox su Windows** (S12: resta): utente dedicato, AppContainer o
    WSL2; serve alla taglia ridotta su un PC. *Da approfondire* · dipende da: la taglia ridotta
    (0.3).
13. **Revisione notturna che propone correzioni** (S13): dopo il banco dei casi veri, con
    l'approvazione dal cruscotto (oggi in sola lettura); di notte la GPU della DGX non è libera, va
    misurato quando. *Da approfondire* · dipende da: la conservazione dei dati (0.1) e il banco
    (2.7).
14. **Sicurezza per valore, fase 5** (S8, giudice sui compiti): non ora, nei registri veri gli
    attacchi sono 0.

**In valutazione (non promesso)**

- Riscontro emotivo dalla voce durante le sessioni di studio, dopo l'interrogazione
  ([`ricerche/2026-10-07-emozioni-voce.md`](ricerche/2026-10-07-emozioni-voce.md)).
- **Un LLM nel cloud a scelta di chi installa** (proposta del 12/10), sotto la stessa impalcatura e
  con l'obiettivo di tenere comunque tutto offline. Il backend compatibile OpenAI basterebbe a
  collegarlo, ma servono analisi apposite prima di qualunque scelta: il principio 9 e la decisione
  [0001](decisioni/0001-tutto-in-locale.md), la privacy dei dati che uscirebbero di casa, i minori,
  i costi, cosa resta comunque locale.

**Scartato**

- Kolibri come base del modulo studio, perché il catalogo in italiano è quasi vuoto (sola
  matematica di Khan Academy) e i contenuti nuovi si creano solo con il servizio online di Kolibri
  Studio, contro il principio «niente cloud»
  ([`ricerche/2026-10-07-kolibri.md`](ricerche/2026-10-07-kolibri.md)).
- *12/10:* la **firma delle versioni delle estensioni** (S11): con la chiave sulla stessa DGX non
  aggiunge niente all'impronta SHA-256 che c'è già.

**Tolte dalla coda il 12/10** (superate; il testo com'era è nella storia di git): «sicurezza per
valore, fase 4» (accesa il 09/10, la fase 5 è S8); «storpiature delle forme chiuse» (fatte il
10/10); «taratura della macchina, fasi 3–6» e «il profilo per il portatile da 8 GB», confluite nella
taglia ridotta (0.3); «i documenti degli agenti, oggi `LocalDelivery`» (falso dal 07/10, vedi 4.11).

## Subito: le proposte delle analisi del 06/10

Decisione del 06/10: farle tutte, da subito, e congelare le funzionalità nuove (solo
correzioni) finché non sono chiuse *[storico: congelamento tolto l'08/10]*.

**Prima analisi** ([`ricerche/2026-10-06-analisi-complessiva.md`](ricerche/2026-10-06-analisi-complessiva.md)):
P1–P11 **fatte** il 06/10. La verifica è nel § 2 della
[seconda analisi](ricerche/2026-10-06-analisi-2.md): P2, P3, P9 e P11 erano fatte solo in
parte, e le Q qui sotto le completano.

| # | Proposta | Stato |
|---|---|---|
| P1 | `stt_correzione` sulla DGX misurata, spenta nel file locale | fatta |
| P2 | Guardiano in parallelo e caldo | fatta; completata da Q3 |
| P3 | Cache del prefisso dopo riavvii | fatta; completata da Q5 |
| P4 | Latenza vera come metrica, con un avviso | fatta |
| P5 | Hook a strati e prove instabili | fatta; completata da Q7 |
| P6 | Guardie doppie tolte, reti con categoria | fatta; corretta da Q2 e Q6 |
| P7 | CLAUDE.md come indice, `docs/aree/` | fatta; tenuta vera da Q8 |
| P8 | `giro` diventa la classe `Ciclo` | fatta; Q10 |
| P9 | Stato della voce per corsia | fatta; completata da Q9 |
| P10 | Costanti comuni (`calliope/testi.py`) | fatta; le 3 copie di `NIENTE` in `politica.py` tolte |
| P11 | Riassunti della compressione con un tempo massimo | fatta; completata da Q11 |

**Seconda analisi** ([`ricerche/2026-10-06-analisi-2.md`](ricerche/2026-10-06-analisi-2.md), § 6):

| # | Proposta | Stato |
|---|---|---|
| Q1 | Un giorno d'uso vero sulla DGX con un elenco di casi | **aperta** *[storico: chiusa il 09/10 con la latenza accettata, vedi sopra]* |
| Q2 | Sfida dopo una foto o un file | fatta (ramo `correzioni-q`) |
| Q3 | Guardiano che non tace: rilevatore nel registro, guasto = guasto per i minori, schede trattenute | fatta (ramo `correzioni-q`) |
| Q4 | Ollama della DGX: 4 modelli e posto per 3 (`OLLAMA_MAX_LOADED_MODELS=4` o embedding fuori) | fatta: embedding a Calliope inattiva (06/10), `OLLAMA_MAX_LOADED_MODELS=4` e `OLLAMA_NUM_PARALLEL=2` sulla DGX (verificato il 07/10) |
| Q5 | P3 completo: storia scaldata già compattata | fatta (ramo `correzioni-q`) |
| Q6 | Reti di sicurezza con un effetto vero (`azione_in_sospeso`, `riferire`) | fatta (ramo `correzioni-q`) |
| Q7 | Hook: legami dei tool d'area, import su Linux, prove manuali, salti parziali | fatta (ramo `correzioni-q`) |
| Q8 | Documenti veri e controllati (`prova_docs_aree`) | fatta (ramo `correzioni-q`) |
| Q9 | Voce per stanza con più satelliti nella stessa stanza | fatta (ramo `correzioni-q`) |
| Q10 | «Esci» in una corsia di satellite: si addormenta e continua | fatta (ramo `correzioni-q`) |
| Q11 | Tetto totale al riassunto della compressione | fatta (ramo `correzioni-q`) |
| Q12 | Ridurre la configurazione (−50 campi) | *12/10: diventa E10 (inventario una tantum, i campi da rendere costanti li sceglie chi amministra)* |
| Q13 | Spegnere nel 26B le reti «modello» a zero scatti (dopo due settimane di registro) | *12/10: diventa E11 (dal 20/10, con il rapporto per rete e per profilo)* |
| Q14 | Spezzare `Brain._reply` | *12/10: diventa E4 (subito dopo il passo 4 del registro, fermando per qualche giorno gli altri lavori su `brain.py`)* |

## Resta da fare (controllato sul codice il 06/10, ripulito il 12/10)

Le voci passate nella coda del 12/10 stanno lassù; qui restano le altre.

**Voce e audio**
- Taratura fine del VAD; falsi risvegli in casa (TV, musica); voci di altri familiari e soglia
  di chi parla da ritarare col secondo familiare.
- Barge-in di livello B completo (DTLN, 4–6 giorni), vedi
  [`ricerche/2026-09-26-cancellazione-eco.md`](ricerche/2026-09-26-cancellazione-eco.md).
- Modello acustico della wake word «computer» (addestramento pronto, da decidere).

**Tool e regole**
- Comandi più frequenti con regole prima dell'LLM («alza», «pausa», «blocca»); `pc_spegni` con
  conferma (non esiste); stato del PC nel messaggio di contesto.
- «Annulla l'ultima modifica» di un documento (le versioni ci sono, il tool no).
- Ponte MCP verso Home Assistant, biblioteca, musica (le estensioni usano già la cornice stdio).
- Recupero dei tool con bge-m3 solo oltre 40–50 tool: oggi i tool sono 65 schemi *[09/10: 72,
  più `esercizi` con un minore in casa]* e la scelta regge; da rimisurare se la qualità scende.
- Casa: conferme a secondo fattore per i domini delicati; direzione opposta (HA che usa
  Calliope come agente per i satelliti).

**Biblioteca e installazioni**
- Prima installazione vera dal catalogo (reindirizzamenti di Hugging Face e GitHub, `.sha256`
  di Kiwix, `/api/pull` vero).
- Altre fonti nella ricerca (WikiMed, Wikivoyage, Wikibooks, Wikiversità, Wikisource,
  Gutenberg con l'indice a pezzi).
- Riparazione all'avvio di chi parla e del modello quando mancano.
- Misure del lettore ZIM e dell'indice sullo Spark (`prove/arm/`).

**Schermi, satelliti, telefono**
- Dalla fase 4 di [`ricerche/2026-10-01-mappe-e-schermi.md`](ricerche/2026-10-01-mappe-e-schermi.md):
  DuckDNS per gli schermi, la card di HA (mappe e percorsi: 3.8; satelliti di stanza senza PC: 3.9).
- Prove con un iPhone vero (audio, schermo acceso, auto) e su un PC Windows pulito.

**Agenti ed estensioni**
- Estensioni: documenti e file ai satelliti dalla porta (i messaggi verso l'esterno: S10).
- Sandbox su Windows, estensioni a orario, Node/JavaScript, documenti degli agenti al satellite:
  nella coda del 12/10 (4.8, 4.10–4.12).

**Auto-miglioramento** (vedi [`visione.md`](visione.md))
- Set di regressione sulle registrazioni (con i dati conservati per 60 giorni, 0.1) e segnale
  acustico per le ripetizioni (`revisione.py`); la revisione notturna è S13 (4.13).

**Windows su ARM**
- Verifica di ogni dipendenza su Windows ARM *[12/10: non serve più al server, che è la DGX
  con Linux; resta per la taglia ridotta su un PC]*.

## Storico: la roadmap di CLAUDE.md al 06/10

1. ~~Primo test reale~~ (fatto). Restano la taratura fine del VAD e la scelta dei
   modelli (Whisper small / medium / large-v3-turbo; LLM 4B contro 7–8B).
2. ~~Configurazione esterna e divisione in package~~ (fatta il 26/09): package
   `calliope/` (`main`, `audio`, `stt`, `tts`, `wakeword`, `brain`, `config`, `tools/`…),
   configurazione in `calliope.yaml`. Le prove in `prove/` importano da `calliope.*`.
3. ~~Wake word dedicata~~ (fatta il 24/09, vedi
   [`docs/ricerche/2026-09-24-wake-word.md`](ricerche/2026-09-24-wake-word.md)).
   Restano la misura dei falsi risvegli in casa (TV, musica), le voci di altri familiari
   ed eventualmente la personalizzazione all'arruolamento.
4. **Barge-in**: livello A fatto il 26/09. `Listener.watch_for_name` ascolta solo la
   wake word mentre Calliope parla. `Speaker.interrupt` la ferma entro 100 ms, e
   `Brain.record_interruption` lascia nella storia solo le frasi pronunciate. Livello B
   leggero fatto il 26/09: `Listener.measure_echo` durante il saluto decide se attivarlo.
   Poi `watch_for_name(voice_ok=…)` controlla l'impronta dopo 0,8 e 1,6 s di parlato:
   solo le persone registrate interrompono, non TV né ospiti. Livello B completo (DTLN,
   4–6 giorni) rimandato, vedi
   [`docs/ricerche/2026-09-26-cancellazione-eco.md`](ricerche/2026-09-26-cancellazione-eco.md).
5. **Tool / function calling**: fatti i tool nativi di base (v0.3) e la memoria per
   persona (26/09). Restano il ponte MCP (Home Assistant, biblioteca, musica) e le
   azioni sensibili con conferma. **Molti tool** (ricerca del 26/09,
   [`docs/ricerche/2026-09-26-tool-e-agenti.md`](ricerche/2026-09-26-tool-e-agenti.md)):
   gemma4:e4b sceglie bene anche con 40 tool piatti (99 %). Regola: elenco fisso per
   livello fino a 25–40 tool, parti variabili subito prima della domanda. Recupero con
   bge-m3 (in `ToolRegistry`) solo oltre 40–50 o per le entità di casa. Agenti solo per i
   lavori a più passi, con un arbitro davanti a Ollama (senza, la voce aspetta 11 s).
   Fatti il 26/09: `calcola`, timer e promemoria (durate e orari convertiti in Python da
   `tempi.py`) e la biblioteca offline (`biblioteca_cerca`, decisione B della visione),
   poi liste, appuntamenti e memoria della casa, e il PC a voce (punto 1 della roadmap 5.3
   di [`docs/ricerche/2026-09-26-controllo-pc.md`](ricerche/2026-09-26-controllo-pc.md):
   8 tool `pc_*` sul portatile, esecutore in processo). Fatti il 27/09 i documenti Word,
   Excel e PDF a voce (`documento_crea`, `documento_modifica`, scrittura con una seconda
   richiesta a Ollama e output strutturati); restano la consegna al PC remoto
   (`LocalDelivery` → «ricevi file» dell'esecutore), l'arbitro davanti a Ollama per le
   generazioni in secondo piano, *[fatti: `RemoteDelivery` il 03/10, arbitro il 02/10 e pausa di vLLM il 04/10]* «annulla l'ultima modifica» (le versioni ci sono) e i
   modelli personali (carta intestata). *[fatti il 03/10: ufficio con docxtpl e python-pptx]* Per il PC restano l'esecutore
   separato via WebSocket (punto 2) *[fatto il 03/10: esecutore remoto sul satellite]*, `pc_spegni` con conferma a regole, lo stato del PC
   nel messaggio di contesto e le regole prima dell'LLM per «alza», «pausa», «blocca».
   Fatta il 01/10 la casa via Home Assistant (direzione Calliope → HA: `casa_comando`,
   `casa_stato`, `casa_integrazione`), provata solo con l'HA finto. *[Superato: HA vero provato il 01/10 sera.]* Restano: la prova a
   casa (sonda, tempi del Raspberry, nomi e alias veri) *[fatta il 01/10 sera]*, i comandi più frequenti con regole
   prima dell'LLM, le conferme a secondo fattore per i domini delicati e la direzione
   opposta (HA che usa Calliope come agente per i satelliti: l'interfaccia `HomeBackend`
   non la impedisce). Fatti il 01/10 il registro delle capacità (`calliope_stato`,
   `python -m calliope.stato`) e le installazioni a voce dal catalogo. Restano: la prima
   installazione vera (reindirizzamenti di Hugging Face e GitHub, `.sha256` di Kiwix), le
   altre fonti in più nella ricerca (WikiMed e Wikivoyage con l'instradamento per tema,
   Wikibooks e Wikiversità con un peso; Wikisource e Gutenberg con l'indice a pezzi di
   ~2 000 caratteri per i testi lunghi: ricerche/2026-10-01-biblioteca-senza-libzim.md),
   la riparazione di chi parla e del modello all'avvio quando mancano (oggi Calliope non
   parte: si installano da terminale). Fatte il 01/10 la biblioteca senza libzim (lettore
   ZIM in puro Python e indice SQLite FTS5, azione `biblioteca_indice`) e Wikiquote per le
   citazioni; resta da misurare sullo Spark (`prove/arm/`).
   Fatta il 02/10 la fase 1 degli **schermi** (server delle schede, pagina kiosk, abbinamento,
   visibilità, schede dei tool, `schermo_mostra`, `schermo_gestisci`). Restano, dal rapporto
   [`docs/ricerche/2026-10-01-mappe-e-schermi.md`](ricerche/2026-10-01-mappe-e-schermi.md):
   fase 2 mappe e luoghi (PMTiles servite con le Range da `schermi/server.py`, scheda `mappa`
   in `schede.py` e nella pagina, indice SQLite dei luoghi, GeoNames, `luoghi_cerca`,
   `mappa_mostra`), fase 3 percorsi (Valhalla, GraphHopper su ARM), fase 4 più schermi e
   satelliti (HTTPS con DuckDNS *[HTTPS con certificato proprio fatto il 02/10, CA di casa il 03/10; DuckDNS no]*, la stanza dal satellite in `Mittente.stanza`, lo schermo
   personale del PC tramite l'esecutore, la card di HA). Anche: il kiosk di Edge
   all'avvio di Calliope (la scheda del timer che scade c'è dal 02/10; manca quella della
   lista cambiata da un'altra stanza verso gli schermi delle altre stanze).
   Fatti il 02/10 gli **agenti in secondo piano** (`calliope/agenti/`: tunnel SSH verso la
   DGX, ciclo d'agente, sandbox, arbitro, `delega_lavoro`, `lavori_stato`,
   `lavori_annulla`, capacità «agenti», `python -m calliope.agenti --prova`, banco
   `prove/prova_lavori.py`). Restano: la prima prova sulla DGX vera (passi in
   `prove/LEGGIMI.md`) e il banco contro `qwen3.6:35b`; *[fatti il 02/10: banco codice 11/12, documenti 10–11/12 con qwen3.6 su vLLM]* llama-server per l'agente (bug
   #16383 di qwen3.6 nel parser di Ollama, prefill a pezzi con `-b 512`); *[superato il 02/10: l'agente usa vLLM]* le domande a metà
   lavoro e i file della persona all'agente (fatti il 03/10) da misurare con il modello vero;
   un isolamento vero della sandbox su Windows *[ancora aperto; dal 03/10 su Windows il codice dell'agente non si esegue]* (utente dedicato o
   WSL2: sulla DGX c'è il container dal 03/10);
   l'esecutore remoto per consegnare i risultati sul PC di chi li ha chiesti. *[fatto il 03/10 per i lavori sui file della persona; i documenti degli agenti usano ancora `LocalDelivery`]* *[superato il 07/10: anche il risultato dei lavori va al portatile con «Lo apro?»]*
6. **Auto-miglioramento** (vedi `docs/visione.md`): registro dei turni in JSONL,
   rilevamento delle frasi ripetute come segnale di errore di trascrizione, set di
   regressione sulle registrazioni, revisione notturna che **propone** correzioni
   misurate. Il prompt, il codice e i permessi non si toccano mai da soli.
7. Migrazione a **RTX Spark**: modelli MoE più grandi e verifica di ogni dipendenza
   su Windows ARM. Gli agenti non aggiungono dipendenze native (job object con ctypes,
   OpenSSH di Windows c'è anche su ARM64); con la DGX in casa basta `collegamento:
   diretto` (o `agenti_url`), senza tunnel.
   Fatto il 02/10 il **satellite minimo** (`calliope/satellite/`: il portatile come
   microfono, casse e schermo di Calliope sulla DGX), il 03/10 l'esecutore remoto del PC
   sulla stessa connessione (`pc_*` e consegna dei documenti al portatile). Restano: la prova con la DGX vera
   (`prove/LEGGIMI.md`) *[fatta dal 02/10]*, più satelliti attivi insieme (una conversazione per stanza) *[fatto il 06/10: corsie]*,
   HTTPS per gli schermi *[fatto il 02/10]*, satelliti di stanza senza PC.
