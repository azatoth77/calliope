# Memoria, agenda, liste, calcoli

*Memoria per persona e della casa, timer, promemoria, appuntamenti, liste, `calcola`, `data_calcola`. Documento d'area: nato il 06/10/2026 dividendo CLAUDE.md (proposta P7 di [`../ricerche/2026-10-06-analisi-complessiva.md`](../ricerche/2026-10-06-analisi-complessiva.md)). Chi lavora su quest'area aggiorna questo file; in CLAUDE.md al più una riga.*

## Moduli

| Stadio | Libreria | Dove |
|---|---|---|
| Memoria per persona | SQLite (`memoria.db`), tool `ricorda` / `dimentica` | `calliope/memory.py` → `Memory`; ricordi inseriti da `Brain._memory_message` |
| Timer, promemoria, appuntamenti | SQLite (stesso file della memoria), thread di scadenza | `calliope/agenda.py` → `Agenda` (`find`, `reschedule`), `announcement`; `calliope/tempi.py` → `parse_duration`, `parse_when`, `parse_shift`, `parse_day_range`, `parse_date`, `anni_compiuti` (età e date: tool `data_calcola`, dal 05/10) |
| Liste della casa | SQLite (stesso file della memoria) | `calliope/liste.py` → `Liste`, `list_key`, `split_items` |

## Note dalla sezione «Stato attuale» di CLAUDE.md (fino al 06/10)

  - **Liste, appuntamenti e memoria della casa** (26/09): liste condivise (spesa, cose da
    fare…), appuntamenti personali con avviso un'ora prima, fatti della casa («ricorda per
    tutti» la password del wifi) visti da tutti i familiari.

  - **Timer e promemoria** (26/09, `calliope/agenda.py` + `calliope/tempi.py`): annunciati con un segnale
    acustico e il nome; i promemoria sopravvivono a un riavvio.

  - **Memoria persistente per persona** (26/09): «ricordati che…» sopravvive alla chiusura.

## Note dalla sezione «Problemi noti» di CLAUDE.md (fino al 06/10)

- **Memoria** (`calliope/memory.py`, 26/09): i fatti sono legati a `UserProfile.id` (non al nome)
  e arrivano al modello come messaggio di sistema **subito prima della domanda**, non nel
  prompt, così la cache del prefisso resta valida e un 4B non deve ricordarsi di chiamare
  un tool per leggerli. Un fatto con lo stesso soggetto sostituisce il vecchio («numero
  preferito è 47» → «è 12»). Ospiti: nulla. Se un tool viene rifiutato per permessi,
  l'errore deve essere esplicito («NON è stata eseguita»): con un semplice «non permesso»
  il modello diceva all'ospite «ho registrato…». Prova: `prove/prova_memoria.py`.

- **Calcoli**: nessun modello piccolo fa bene i conti a mente. Dal 26/09 c'è `calcola`
  (`calliope/tools/builtin.py`), un valutatore sicuro su `ast`, con la trigonometria in gradi. Oltre al
  risultato restituisce `da_dire` («circa 824,4 mila miliardi»). Prova `prove/prova_calcola.py`:
  16/16. Nella descrizione servono esempi espliciti: «per» = ×, «alla decima» = `**10`;
  senza, «17 per 6» diventava 17/6. **I numeri vanno scritti in cifre** (lo dice il prompt):
  Piper/espeak li legge bene («1.024» → «mille ventiquattro»), mentre il modello li scrive
  male in lettere.

- **Timer e promemoria** (26/09): il modello passa durata e orario **come detti**
  («mezz'ora», «domani alle 9») e `calliope/tempi.py` li converte (prova `prove/prova_tempi.py`: 37
  casi). Allo scadere l'agenda sveglia `Listener.listen(wakeup=…)`, che si interrompe
  solo se nessuno sta parlando; Calliope suona `Speaker.chime()`, annuncia con il nome e
  resta in ascolto. «Alle 6» alle 14 vale le 18 (primo orario futuro). I timer sono della
  casa (anche per gli ospiti), i promemoria sono personali (familiari). I risultati dei
  tool hanno una `conferma` già pronta: senza, il modello ripeteva la richiesta invece di
  confermarla. Prova su Ollama `prove/prova_agenda.py`: 14/14.
  **Cambiare una voce già messa** (03/10: «Mettimi un timer di un secondo», poi «impostalo
  di un minuto» ne avviava un secondo): `timer_imposta`, `promemoria_imposta` e
  `appuntamento_aggiungi` hanno `cambia` (`imposta` | `aggiungi` | `togli`), invece di un tool
  nuovo: il modello sceglieva già il tool giusto, gli mancava solo il modo di dire «quello
  già messo», e il prefisso cresce di un parametro, non di uno schema. Il modello decide se si
  cambia (con `AGENDA_MSG` di Brain prima della domanda nei turni dopo, come il riferimento
  della casa: `riferimento_agenda`, rete spegnibile); quale voce lo decide `Agenda.find` (una
  parola vera del nome, altrimenti l'ultima messa o cambiata dalla persona). Durate e orari
  come detti: «aggiungi»/«togli» partono dalla scadenza attuale, `tempi.parse_shift` corregge
  «imposta» con «5 minuti in più» (regola `durata_relativa`), «spostalo alle 9» resta nel
  giorno della voce. Stessa riga (id e `created`): la scheda `timer:<id>-<creazione in ms>`
  si aggiorna e sale in cima; l'avviso dell'appuntamento si rifà. Il timer da cambiare già
  suonato: se ne avvia uno nuovo e la conferma lo dice. Ollama (gemma4 e4b, 9 conversazioni
  × 2 giri in `prova_agenda`): 16/18, poi **18/18** dopo aver scritto che con «imposta» la
  durata detta sostituisce la vecchia («impostalo di cinque minuti» diventava «aggiungi»);
  i casi contrari («un altro timer», «che ore sono?», «anche un timer per le uova») 6/6.

- **Liste, appuntamenti, memoria della casa** (26/09). Liste (`calliope/liste.py`) della
  famiglia, non degli ospiti: le voci si confrontano senza articoli, maiuscole e vocale
  finale («le uova» = «uovo»), così niente doppioni e «ho preso il latte» toglie la voce
  giusta; attenzione, per lo stesso motivo due voci quasi uguali («pila AA», «pila AAA»)
  sono la stessa. Le conferme usano la preposizione articolata («alla lista della
  spesa»): «in la lista» suonava male. Appuntamenti: tipo `appuntamento` nell'agenda, con
  un `avviso` figlio (colonna `parent`) `appuntamento_anticipo_min` prima; annullando
  l'appuntamento sparisce anche l'avviso, e gli avvisi non compaiono negli elenchi.
  `parse_when` non conosce il passato: «ieri alle 9» diventava «oggi alle 21», quindi
  `ieri`/`scorso` si rifiutano prima. Memoria della casa: `ricorda(per_tutti=true)` salva
  con persona `casa` (`memory.HOUSE`); `Brain._memory_message` aggiunge il blocco «Cose
  della casa» per chi è riconosciuto. Un rifiuto per permessi ora conta come fallito
  in `Brain.last_tools` (prima risultava riuscito nel registro dei turni). Prova su
  Ollama `prove/prova_casa.py`: 42/42 in 2 giri, prima frase mediana 0,49 s.

## «Si chiama» non è un ordine (06/10, prova e2e)

`sicurezza.instruction_fact` rifiutava «il mio gatto si chiama Briciola» come
`ricordo_istruzione`: «chiama» era tra gli ordini anche con un pronome davanti. Ora conta come
ordine solo senza «si/mi/ti/ci/vi/lo/la/li/le/ne» prima; casi in `prova_testo` (tre ordini, tre
nomi).

## Un ricordo non si cancella a una domanda (06/10, prova e2e, giro 1247)

Carlo: «Qual è il mio numero preferito?», trascritto «O no è il mio numero preferito.»; il 26B ha
detto «ho rimosso il numero 47 dai tuoi ricordi», la rete sulle azioni dichiarate l'ha spinto a
chiamare `dimentica` e il ricordo è sparito («Ho dimenticato il tuo numero preferito»).
- **Cancellare va chiesto** (`politica.Classe.verbo_sempre`, `politica.chiesto_di_dimenticare`,
  `DIMENTICA_VERBI`): `dimentica` si esegue solo se la frase ha un verbo di cancellazione non
  negato («dimentica», «cancella», «scordati», «togli», «elimina», «levalo», «non ricordare più»),
  anche con la conversazione pulita; altrimenti «Non me l'hai chiesto: vuoi che dimentichi «…»?»
  (regola `politica_cancellazione_non_chiesta`) e il «sì» (una parola di consenso: un «no» non
  basta anche se il modello richiama il tool) la esegue. Contrari: «qual è…?», «o no è…», «ti
  ricordi…?», «non è più…», «non dimenticarlo», «non lo cancellare».
- **Recuperabile per 5 minuti** (`Memory.RECUPERO_S`, `Memory.recupera`): `forget` mette da parte
  quello che toglie (in memoria, l'ultima cancellazione per persona); la conferma di `dimentica`
  dice «Se è stato un errore, dimmi «annulla» entro 5 minuti» e il risultato ha `se_annulla` per
  il modello; `ricorda` con lo stesso fatto (somiglianza ≥ 0,75 e gli stessi numeri), «tutto» o
  «annulla» lo rimette con le sue date (regola `ricordo_recuperato`), prima del controllo
  `ricordo_non_detto`. «… è 12» dopo aver dimenticato «… è 47» è un fatto nuovo, non un recupero.
- Misure con gemma4 e4b locale: «Qual è il mio numero preferito?» e «O no è il mio numero
  preferito.» 0/10 `dimentica` (anche con il ricordo detto nella stessa conversazione: 0/10),
  «Dimentica il mio numero preferito.» 5/5 cancellato; «dimentica…» poi «No, annulla! Ricordalo.»
  4/4 ricordo tornato. Il 4B non riproduce l'errore del 26B (sta a `prova_politica`, con il
  modello finto). Con il ricordo appena detto nella stessa conversazione il 4B risponde a
  «Dimentica il mio numero preferito.» «Dimentica il fatto che…» senza tool 4/5 volte, uguale sul
  codice di prima (0/5): difetto del 4B, non di questa correzione.

## Età e compleanni dai profili (07/10, DGX 06/10 sera, ramo `eta-vuoti`)

Casi veri (qui con nomi di fantasia): Bianca, minorenne registrata con la data di nascita
(10/09/2012), chiede «Quanti anni ho?» → `data_calcola(cosa="eta", data=<oggi>)`, il tool
risponde «compie 0 anni proprio oggi» e il 26B dice «oggi è il tuo compleanno e compi 14 anni»
(i 14 anni venivano dai dati del turno del minore). Poi il genitore: «Quando è il compleanno di
Bianca?» → ricerca nelle conversazioni, e «mancano ancora 309 giorni» contati a mente (erano 339).
La data di nascita era nel profilo (`speakers.json` v2, `nascita`), il modello non la vedeva.
- **`data_calcola` con `persona`** («io» o il nome di una persona registrata): la data di nascita
  la prende il programma dal profilo; `eta` e `giorni_mancanti` danno anni, prossimo compleanno e
  giorni che mancano (`_dati_nascita`), con `da_dire` («Hai 14 anni; ne compi 15 il 10 settembre
  2027, tra 338 giorni.»). `data` non è più obbligatoria (resta `cosa`, così `{}` si ferma).
- **La data di oggi come nascita si rifiuta** (regola `data_eta_oggi`): `eta` con la data di
  oggi (anche «oggi») e senza `data2` risponde con l'errore e `cosa_fare` (persona, o chiedere la
  data). Contrari: una data di nascita vera, `giorni_mancanti` a «oggi» («È oggi.»).
- **Privacy** (`_vede_nascita`): la propria sì; di un altro solo chi amministra e i tutori
  (`minori.e_tutore`); un familiare non tutore o un minore per un adulto ricevono la frase pronta
  (regola `nascita_riservata`); gli ospiti non hanno un profilo («non so chi sta parlando»).
- **Dati del turno**: la data di nascita di chi parla, per tutti quelli che ce l'hanno
  (`minori.dato_nascita`: «data di nascita 10 settembre 2012 (14 anni)»), dopo il preset del
  minore; `chi_parla` dà anche età e compleanno; `elenca_utenti` li dà a chi può saperli.
- Misura con gemma4 e4b locale (script di misura fuori dal repository, 7 domande: «Quanti anni
  ho?», «Quando è il mio compleanno?», compleanno, giorni e anni di Bianca chiesti dal genitore,
  «Parliamo di Bianca, che cosa sai di lei?», «Bianca è registrata? Riconosci la sua voce?»):
  codice di prima **2/14**, dopo **18/21** (3 giri). Restano 2/3 «Quanti anni ha Bianca?» in cui il
  4B chiede la data invece di chiamare il tool (con la descrizione «non chiederla prima» da 0/2 a
  1/3), e 1/3 «quanti giorni mancano…». Prima frase mediana 0,88 → 2,4 s, ma prima erano quasi
  tutte risposte senza tool («ho bisogno della data di nascita»). Da rimisurare col 26B.
- Prova: `prove/prova_eta_utenti.py` (35 controlli).
