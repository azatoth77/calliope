# 0030. I conoscenti: voci sconosciute di adulti col nome dedotto dalla conversazione

- **Stato**: accettata (14/10/2026, decisioni di chi amministra), fatta il 14/10 sul ramo
  `stanza-conoscenti` dietro `stanza_conoscenti` (di serie spento)
- **Area**: [stt-tts](../aree/stt-tts.md), [contesto-conversazione](../aree/contesto-conversazione.md),
  [sicurezza-politica](../aree/sicurezza-politica.md); tool in [`architettura-tool.md`](../architettura-tool.md)

## Contesto

Con la conversazione di stanza ([0029](0029-conversazione-di-stanza.md)) Calliope sa chi ha detto
cosa vicino ai satelliti, ma chi viene spesso in casa senza essere della famiglia (un collega, un
vicino, il papà di un amico del ragazzo) resta per sempre «voce non riconosciuta»: le sue righe
stanno solo in memoria, non si cercano, e il blocco della stanza non dice chi è. Il progetto
([`2026-10-13-conversazione-di-stanza.md`](../ricerche/2026-10-13-conversazione-di-stanza.md)
§ 3.10, passo 7) lasciava gli ospiti come argomento secondario. Il 14/10 chi amministra ha deciso
che queste voci diventino **conoscenti**, con il nome che Calliope ricava da come li chiamano.

## Decisione

1. **Deduzione automatica, conferma di chi amministra.** Calliope raggruppa i segmenti delle voci
   non riconosciute per somiglianza dell'impronta (gruppi **in memoria**, per installazione) e
   deduce il nome dal contesto: vocativi e saluti seguiti dal parlato di quella voce («Ciao
   Marco!» → risponde la voce X; «Marco, tu che dici?» → parla X), presentazioni («sono Marco»),
   più indizi concordi; i nomi di cui si parla in terza persona non contano (detti dalla voce
   stessa contano contro). Oltre una soglia propone a chi amministra **sullo schermo personale**
   (mai a voce davanti all'ospite, mai sugli schermi di stanza): «Ho sentito una voce nuova che
   chiamate Marco: la salvo come conoscente?», con un pezzo breve di trascrizione e Sì / No / un
   nome diverso. **Senza conferma non si salva nulla** (nessuna impronta su disco; la scheda non
   va nella cronologia su disco), e un **No** non ripropone la stessa voce (finché Calliope gira:
   per non salvare l'impronta di chi ha detto no, dopo un riavvio la voce rifiutata non è più
   ricordata).
2. **Il conoscente**: un profilo di tipo «conoscente» con nome, cognome e nota facoltativi e
   l'impronta della voce, in un file suo (`conoscenti.json`), **fuori** dal registro delle voci
   della famiglia (`speakers.json`): così nessun percorso di riconoscimento dei comandi lo vede e
   resta un **ospite** a ogni effetto (nessuna azione di chi amministra né dati della famiglia;
   per la conservazione la categoria `conoscente` vale come un ospite, salvo la stanza).
   Riconosciuto nelle volte dopo, col nome nelle righe della stanza; le sue frasi vanno su disco
   con la tenuta della stanza (60 giorni) e si cercano come quelle della famiglia (stessi
   permessi: chi c'era); le frasi delle voci ancora sconosciute restano solo in memoria.
3. **Cancellazione**: impronta e profilo si cancellano se la voce non si sente da 6 mesi
   (`conoscenti_scadenza_giorni: 180`), con «Calliope, dimentica Marco» (solo chi amministra, a
   voce, con la domanda e il sì) e con `calliope conserva --svuota`; cancellando si tolgono anche
   le sue righe su disco (e in memoria tornano di una voce non riconosciuta).
4. **Omonimie** (aggiunta di chi amministra, 14/10). Il nome dedotto non è un'identità:
   - l'identità di un conoscente è la sua **impronta**; il nome è un'etichetta;
   - alla conferma chi amministra può aggiungere **cognome** e una **nota** breve («collega di
     Carlo», «papà di Luca»), che distinguono gli omonimi nelle righe della stanza, nella ricerca
     («cosa ha detto Marco Rossi?»), nelle proposte e in «dimentica Marco» (con più Marco Calliope
     chiede quale, dicendo cognome e nota);
   - una voce nuova con il nome di un conoscente già salvato ma un'altra impronta: la proposta lo
     dice («un altro Marco, non Marco Rossi?») e i due profili **non si fondono mai**; lo stesso
     nome, cognome e nota di un altro si rifiutano (si chiede di distinguerli);
   - un nome uguale a quello di un familiare **non si esclude**: si propone come conoscente
     omonimo, segnalandolo.
5. **Promozione a familiare** (aggiunta di chi amministra, 14/10). Un conoscente diventa
   familiare solo se lo promuove chi amministra (mai da sé, mai un altro familiare), per la stessa
   via sicura dei cambi di livello di oggi (`registra_utente`): a voce riconosciuta sopra soglia
   (lo scritto chiede la voce; zona grigia no), tool pericoloso chiesto nel turno, con la frase di
   sfida se ci sono dati non fidati di mezzo, più la domanda e il sì. Il profilo conserva id,
   impronta, nome e cognome; entra in `speakers.json` con i permessi e le regole dei familiari (la
   scadenza dei 6 mesi non vale più; conservazione e ricerca come la famiglia; le sue righe su
   disco passano a lui); Calliope propone di rifare la registrazione della voce per un'impronta
   migliore, senza obbligo. Un minore promosso vuole la data di nascita e i tutori, adulti di casa
   (`minori.py` com'è). Al contrario un familiare torna conoscente, o un conoscente si toglie,
   solo da chi amministra; chi amministra e i minori non tornano conoscenti.
6. **Minori sconosciuti**: un gruppo la cui voce sembra di un bambino non si propone mai, se c'è
   uno stimatore dell'età della voce; oggi non c'è, e la proposta lo dice («Non so dire l'età
   dalla voce: se è un bambino rispondi No»).
7. **Misure senza parole** in `calliope stato --turni` (sezione «Stanza», riga «Conoscenti»):
   gruppi, proposte (con omonimi), arrivate a uno schermo, conferme, rifiuti, discordi, voci di
   bambino, dimenticati, scaduti, promossi, tornati conoscenti. Mai nomi né parole.
8. **Default prudente**: `stanza_conoscenti: false`; spento non parte niente (né gruppi né file).

## La regola sul testo

La deduzione del nome è una regola deterministica sul testo, `conoscente_nome`
([0008](0008-regole-deterministiche-solo-in-forma-chiusa.md), principio 10): riconosce forme chiuse
e brevi (saluto + nome, nome + virgola in testa, «…, nome?» in coda, «sono / mi chiamo + nome»),
non decide il significato di ciò che dice la persona e non fa niente da sé: il suo solo effetto è
una **proposta** a chi amministra, che decide e può rispondere No o correggere il nome. I contrari
sono in `prove/prova_stanza_conoscenti.py`; le misure (non il registro dei turni: le righe della
stanza non sono turni) hanno gli eventi della regola.

## Cosa cambia nelle decisioni di prima

- **[0029](0029-conversazione-di-stanza.md) punto 5** («ospiti mai su disco né nella ricerca»):
  resta vero per le voci **non confermate**; un conoscente confermato da chi amministra è un
  ospite per i permessi, ma le sue righe della stanza si tengono e si cercano come quelle della
  famiglia. `conserva.decidi` ha una categoria nuova, `conoscente` (solo `stanza`).
- **[0028](0028-decisioni-roadmap-12-10.md) T1**: invariata per turni, voce, eventi e
  conversazioni (un conoscente non ne ha su disco).
- **Livelli** ([`architettura-tool.md`](../architettura-tool.md) § 5): nessun livello nuovo; il
  conoscente è un **tipo** di profilo con il livello ospite, fuori dal registro delle voci.

## Alternative considerate

- **Il conoscente in `speakers.json`** con un campo `tipo`: scartata; ogni punto che oggi tratta
  «voce riconosciuta = familiare» (`SpeakerContext.profile_level`, compagnia, conferme, minori)
  avrebbe dovuto imparare l'eccezione, e una dimenticanza avrebbe dato a un ospite i permessi di
  un familiare.
- **Il nome dal modello** (la stanza riletta dall'LLM): rimandata; costa una passata per ogni
  scambio, e la regola con la conferma umana basta per una proposta.
- **Escludere i nomi della famiglia**: era la prima decisione, superata dall'aggiunta sulle
  omonimie (punto 4).
- **Ricordare i No su disco**: scartata; vorrebbe dire salvare l'impronta di chi non ha
  acconsentito.
- **Promozione dallo schermo** con un tasto: scartata; oggi un cambio di livello vuole la voce di
  chi amministra (lo scritto da uno schermo personale vale al più familiare).

## Conseguenze

- Codice: `calliope/stanza/conoscenti.py` (gruppi, regola, proposte, file, scadenza, promozione),
  `calliope/tools/conoscenti.py` (`conoscenti`, `conoscente_livello`), `POST /api/conoscenti` e
  la scheda `conoscente` degli schermi; la stanza (`ascolto.py`) riconosce i conoscenti e passa
  le righe alla deduzione; la tenuta ha la colonna `nota` e sposta le righe al cambio di tipo.
- Prova: `prove/prova_stanza_conoscenti.py` (a secco, impronte finte, con i contrari).
- Rischi dichiarati: una voce clonata o una registrazione che si fa chiamare per nome produce al
  più una proposta, che chi amministra vede con il pezzo di trascrizione; il conoscente non ha
  permessi. Un gruppo può mescolare due voci simili (impronta sopra soglia): la proposta lo
  mostrerebbe con un nome solo, e il conoscente salvato riconoscerebbe entrambe come «Marco»; da
  misurare sulla DGX (conferme e rifiuti) prima di accenderlo.
- Da fare: lo stimatore dell'età della voce (oggi nessun modello). Fatti il 14/10 sera (ramo
  `conoscenti-avvisi-2`): il nome del conoscente nei turni rivolti a Calliope (solo un'etichetta,
  livello ospite, la famiglia vince sempre) e le presenze dei conoscenti (memoria e disco, nel
  blocco della stanza, spostate alla promozione).

## Fonti

- Decisioni di chi amministra del 14/10 (tre punti, più le aggiunte su omonimie e promozione)
- [`2026-10-13-conversazione-di-stanza.md`](../ricerche/2026-10-13-conversazione-di-stanza.md)
  § 3.10 e § 6 (passo 7)
- Decisioni [0008](0008-regole-deterministiche-solo-in-forma-chiusa.md),
  [0028](0028-decisioni-roadmap-12-10.md), [0029](0029-conversazione-di-stanza.md)
