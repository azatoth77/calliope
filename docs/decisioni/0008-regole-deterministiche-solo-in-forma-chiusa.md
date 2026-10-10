# 0008. Regole deterministiche sul testo solo nei casi stretti

- **Stato**: accettata (01/10/2026, principio 10); rafforzata il 09/10 dall'analisi delle
  incongruenze; evolve nella macchina a stati ([0022](0022-macchina-a-stati-del-dialogo.md))
- **Principi**: 10 di [`CLAUDE.md`](../../CLAUDE.md)
- **Area**: [voce-e-regole](../aree/voce-e-regole.md)

## Contesto

Nei primi giorni Calliope aveva accumulato regole a espressioni regolari prima, dopo o al posto del
modello: parole d'uscita, stop, «sì → esegui l'azione in sospeso», correzioni degli argomenti.
L'inventario del 01/10 (29 regole provate sui dati veri, 181 turni e 292 frasi, e su 72 frasi
costruite, ~470 richieste a Ollama) ha trovato che le regole pericolose lo sono per pochi motivi
ricorrenti: cercano una parola **dentro** la frase invece di riconoscere la frase intera, o
confrontano per somiglianza parole che non sono storpiature. Esempi: «chiudi» ovunque spegneva
Calliope («chiudi le tapparelle»); lo stop prendeva la prima parola («Ok, aprilo» ignorato).

Una misura ha deciso il metodo. Dopo «Lo apro?», con un semplice «Sì grazie» il modello senza
contesto apriva il file 0 volte su 8. Con una riga di contesto «azione in sospeso» apriva **24 volte
su 24** quando la persona acconsentiva e **0 su 27** quando rifiutava o chiedeva altro. La regola
«sì → apri» faceva 8/8 sui sì, ma apriva anche in 3 casi su 9 sbagliati («Sì, ma prima aggiungi la
data»).

## Decisione

Il **significato** di ciò che dice la persona lo decide il modello. Una regola sul testo è ammessa
solo se:

1. è un vincolo di sicurezza o di permesso;
2. è una conversione o una correzione della forma di una scelta già fatta dal modello;
3. riguarda ciò che il modello non vede (audio, trascrizione, storpiature del nome e di «esci»);
4. riconosce una **forma chiusa e breve per intero** (mai una parola dentro la frase), con un
   effetto reversibile.

Tutto il resto è una **spinta** (un messaggio che chiede al modello di riconsiderare) o un
**contesto del turno**. Ogni regola ha i suoi casi contrari in `prove/prova_testo.py` e scrive il
suo nome nel registro dei turni (campo `regole`). Se il modello sbaglia meno di una volta su dieci,
niente regola.

## Alternative considerate

- **Regole per ogni caso visto**: scartate, generano falsi positivi che nessuno vede.
- **Tutto al modello, nessuna regola**: scartato per ciò che il modello non vede e per le reti che
  servono davvero (`TextCallGuard`, che recupera una chiamata di tool scritta come testo: 8 su 57
  nei dati veri, «la regola più utile del progetto»).

## Conseguenze

- Il 09/10 l'analisi delle incongruenze ha contato **276 nomi** di regole: in 1437 turni ne sono
  scattate 132, 180 mai. La domanda «questo sì basta?» era decisa in **sei punti** con criteri
  diversi; le uscite valutate prima della proposta facevano addormentare Calliope su «Sì, puoi
  andare». Regola di metodo da allora: prima di aggiungere una regola su consenso, identità o
  conversazione, cercare se lo stesso ingresso è già giudicato altrove e cambiare quella.
- La risposta strutturale è la macchina a stati del 10/10: la macchina tiene lo stato, il modello
  interpreta, una corsia veloce riconosce solo le forme chiuse ([0022](0022-macchina-a-stati-del-dialogo.md)).

## Fonti

- [`2026-10-01-regole-deterministiche.md`](../ricerche/2026-10-01-regole-deterministiche.md)
- [`2026-10-09-regole-incongruenze.md`](../ricerche/2026-10-09-regole-incongruenze.md)
