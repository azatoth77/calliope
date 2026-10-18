# 0031. Le parole dei minori di casa si conservano come quelle degli adulti

- **Stato**: accettata (16/10/2026, decisione di chi amministra dopo i log del 15/10 sera), fatta
  il 16/10 sul ramo `issue-104-minori-conserva` (issue #104); **aggiornata il 16/10** dopo la
  revisione della PR #106 (consenso alla voce implicito nella registrazione, punto 2; il dubbio
  come lo scrive il ciclo, punto 3; il limite del journal, punto 8) e dopo la issue #108 (il «sì»
  breve di ogni tutore, punto 2; la maggiore età e i conoscenti, conseguenze). Supera il punto 1 (T1) della
  [0028](0028-decisioni-roadmap-12-10.md) per i minori di famiglia: «di minori e ospiti mai»
  diventa «degli ospiti mai». **Eccezione a tempo dal 18/10**: durante la valutazione
  (`conserva_valutazione_fino`) anche gli ospiti, vedi [0032](0032-valutazione-conserva-tutto.md).
- **Area**: [contesto-conversazione](../aree/contesto-conversazione.md), [minori](../aree/minori.md);
  codice in `calliope/conserva.py` (il solo posto che decide) e `calliope/tools/conserva.py`

## Contesto

Dal 12/10 ([0028](0028-decisioni-roadmap-12-10.md) T1) turni, eventi, voce e archivio delle
conversazioni si tenevano 60 giorni solo per gli adulti riconosciuti; dei minori restavano i
numeri, il registro degli eventi stava in memoria, la conversazione nell'archivio della sessione
(persa al riavvio) e il journal mascherava le loro frasi («(una frase di un minore)»).

Il 15/10 sera una minore registrata (fascia bambini) ha parlato con Calliope per circa 25 minuti
(29 risposte, 42 turni giudicati dal guardiano): su disco ne restavano solo i numeri (`testo` e
`risposta` null nel registro dei turni, `conserva: {testo: false, motivo: minore}`), e nel journal
le sue frasi erano mascherate tranne quelle dell'arruolamento (la maschera guardava chi
amministrava, problema 11 dell'analisi). Chi amministra non poteva rileggere né misurare metà
dell'uso vero di casa: banco dei tool, regressione, soglie e guardiano a posteriori vedevano solo
gli adulti.

## Decisione

Testuale, di chi amministra (16/10): «la privacy in casa di un minore non esiste e ciò che dice
DEVE finire nel db e nel disco».

1. **I minori di casa come gli adulti**: testo dei turni, registro degli eventi, archivio delle
   conversazioni (anche la conversazione in corso salvata) e journal, per gli stessi
   `turn_log_days` (60) giorni e con gli stessi comandi per svuotare (`calliope conserva --svuota
   [--persona]`, `dati_conservati` azione `svuota`). I tutori le rileggono come già potevano per la
   sessione (`conversazioni_visibili_ai_tutori`, a ogni età dal 14/10).
2. **La voce del minore col consenso dei tutori, implicito nella registrazione** (decisione di chi
   amministra del 16/10: «alla registrazione del minore da parte dell'amministratore, il consenso è
   implicito»). Registrando un minore (`registra_utente`, solo chi amministra, con la voce e la
   frase di sfida) chi amministra dà il consenso: nel profilo `voce_conservata`, la data e
   `voce_conservata_da` (chi registra), senza una domanda in più. Un minore **già registrato** con
   i tutori nel profilo ha il consenso senza domanda. Il consenso vale finché c'è un tutore
   valido: chi l'ha dato, se il suo profilo esiste ed è ancora tutore (`minori.e_tutore`), o uno
   dei tutori del profilo che esiste ancora; senza tutori validi, niente voce. Lo **revoca** un
   tutore a voce, con la persona minore come argomento (`dati_conservati(revoca_voce, persona)`) e
   la **stessa conferma di «svuota»** (voce sopra soglia, o un «sì» breve con l'impronta
   compatibile: un minore accanto, o il tutore nel dubbio col minore, non decide; dal 16/10,
   issue #108, il «sì» breve compatibile vale per ogni tutore, anche se non amministra); le
   registrazioni si cancellano. Dopo una revoca lo ridà a mano un tutore, con la domanda e il «sì»
   con la stessa conferma. **Il minore da solo non dà né revoca il consenso alla sua voce.** Un
   adulto che non amministra non può registrare un minore, e quindi non dà nessun consenso;
   chi amministra che registra un minore con altri tutori resta scritto come chi l'ha dato, e
   vale il consenso dei tutori del profilo. Il consenso dei tutori vale finché la persona è
   minore: da adulta lo ridice lei.
3. **Nel dubbio tra un adulto e un minore** (`incerta`, `minore_vicino`, `minore_incerto`, il
   proprietario di un satellite personale incerto con un minore) **si tiene il testo ma non la
   voce**: sono due persone di casa, il testo va sotto la persona decisa dal ciclo; l'audio può
   essere dell'altra persona, come in compagnia. Il ciclo scrive questi turni con `modo:
   conversazione` e il segno del dubbio nel campo `voce`: il segno li distingue dalla zona grigia.
   `incerta` vale solo con la voce migliore sopra `speaker_id_threshold`: sotto, `piu_protetto` ha
   dato al minore una voce di nessuno (un ospite vicino al suo profilo) e il turno resta fuori.
4. **Restano fuori dal disco come prima**: gli ospiti e le voci non riconosciute (nessun profilo),
   la zona grigia (`modo: conversazione`). I **conoscenti** restano come deciso il 14/10 sera
   ([0030](0030-conoscenti.md) punto 9), e un bambino non si salva mai come conoscente.
5. **La pulizia all'avvio e la rotazione non toccano più i dati dei minori**: il registro dei
   turni di prima, i registri degli eventi e le conversazioni su disco di un minore restano.
6. **Niente migrazioni**: le parole dei minori già tolte dal 12 al 16/10 (registro dei turni,
   eventi in memoria, archivio della sessione) non tornano. Calliope non è in produzione.
7. **Permessi e guardiano invariati**: conservare non cambia cosa un minore può fare né il
   guardiano; la scelta di forma della frase dopo un tool (System 1, che con un minore lascia
   parlare il modello) passa da `minori.parla_minore` invece che dalla maschera del journal.
8. **Limite accettato, il journal**: una voce senza profilo che `minori.piu_protetto` attribuisce
   a un minore (vicina al suo profilo, sotto soglia) vale quel minore per i permessi e per la
   prudenza, e le sue frasi vanno nel journal in chiaro (`console_riservata` guarda solo il
   livello ospite); su disco no (punto 3). Prima del 16/10 erano mascherate perché lo erano tutte
   quelle dei minori.

## Alternative considerate

- **Solo il testo, mai la voce del minore**: scartata; chi amministra vuole i minori come gli
  adulti, e la voce degli adulti è già col consenso.
- **Una durata più corta per i minori**: non chiesta.
- **Il journal ancora mascherato**: scartata; sarebbe l'unico posto diverso dal disco.
- **Il consenso alla voce dato dal minore stesso** (dai 14 anni, come l'art. 8 del GDPR per i
  servizi online): scartata per scelta di chi amministra, in casa decidono i tutori.

## Conseguenze

- Più dati sensibili sulla DGX (parole di bambini): restano 600/700, fuori da git (`registro/`
  e `conversazioni.db` ignorati), svuotabili; `prova_dati_privati` resta nell'hook. Nessun invio.
- Un dubbio tra un adulto e un minore attribuito alla persona sbagliata finisce nel registro
  dell'altra persona di casa: accettato (stessa famiglia); la voce resta fuori.
- Nessun costo di latenza né di GPU: la conservazione non usa il modello.
- Nessuna regola sul testo nuova (principio 10).
- **La maggiore età** (issue #108): compiuti i 18 anni il sì dei tutori non vale più e la prima
  rotazione cancella tutte le registrazioni della voce della persona; nessun avviso prima (sono
  dati per le misure e toglierli è la direzione sicura), ma `dati_conservati stato` le dice perché
  e il journal ne tiene una riga con l'id; il suo sì da adulta vale subito.
- **Conoscenti** (issue #108): con `incerta` sopra soglia il conoscente non si cerca (la famiglia
  vince), quindi accendere `stanza_conoscenti` non cambia il rischio accettato del punto 3.

## Fonti

- Issue #104 (analisi completa con i punti del codice), log della DGX del 15/10 sera.
- [0028](0028-decisioni-roadmap-12-10.md) T1; [0029](0029-conversazione-di-stanza.md) punto 5 (il
  testo della stanza già per tutta la famiglia, minori compresi); [0030](0030-conoscenti.md).
- Documenti d'area: [contesto-conversazione](../aree/contesto-conversazione.md) e
  [minori](../aree/minori.md), voci del 16/10.
