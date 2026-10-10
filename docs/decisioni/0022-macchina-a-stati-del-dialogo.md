# 0022. Lo stato del dialogo come macchina a stati, con l'interprete del modello

- **Stato**: **proposta, in corso** (progetto del 10/10/2026; passo 0 e passo 1 in lavorazione)
- **Area**: [voce-e-regole](../aree/voce-e-regole.md), [sicurezza-politica](../aree/sicurezza-politica.md)

## Contesto

L'analisi delle regole del 09/10 ([0008](0008-regole-deterministiche-solo-in-forma-chiusa.md)) ha
mostrato che lo stato del dialogo esiste ma è sparso: tre contenitori con vite diverse (la
conversazione per persona, il contesto per satellite, la risposta in corso) e una decina di stati
paralleli nei servizi (offerte dei lavori, delle installazioni, proposta dello sviluppo, cancelli dei
minori, esercizi). Domande come «c'è una proposta aperta?», «è la stessa persona?», «questo sì
basta?» hanno da tre a sette risposte. Dal codice e dal registro (1437 turni, 02–09/10) escono dieci
stati che rischiano di non essere gestiti: per esempio una proposta persa da uno stop detto mentre
Calliope la sta facendo, o un «no» a una domanda dell'agente che lascia il lavoro ad aspettare due ore.

## Decisione

Un modulo (`stato_dialogo.py`, nome provvisorio) con **uno stato per persona** (conversazione, la sola
proposta parlata, la sfida legata a quella proposta, intenzioni e rifiuti, attese in coda) e **uno per
satellite** (finestra d'ascolto, parla/ascolta, interruzione, compagnia). Riceve eventi e restituisce
azioni; non chiama mai il modello né i tool.

Due decisioni di chi amministra (10/10):

1. **La macchina non interpreta il linguaggio.** Tiene lo stato e i vincoli; il **modello** interpreta
   la risposta della persona e la restituisce strutturata con un tool (`proposta_rispondi(esito, …)`);
   una **corsia veloce** deterministica riconosce solo le forme chiuse brevi dette per intero («sì»,
   «no», «annulla»); la macchina **valida** l'esito ed esegue solo la proposta che ha in mano, con gli
   argomenti che ha in mano. Un errore del modello costa al più una conferma in più, mai un'azione
   sbagliata.
2. **Gli scambi tra macchina e modello non inquinano la conversazione**: lo stato è effimero nel turno,
   la storia resta pulita.

Le priorità della frase stanno in un posto: minori come pavimento → sfida → proposta → interruzione →
uscite → cortesia → modello. «Questo sì basta?» ha una funzione sola (`consenso.basta`).

**Piano**: otto passi rilasciabili uno per uno. Con il «percorso corto» deciso lo stesso giorno, in
ombra solo l'interprete (passo 1) e il consenso unico (passo 2); le parti senza rischio si accendono
direttamente. Prima di tutto il **passo 0**: una prova per ciascuno dei dieci stati a rischio e le
correzioni subito.

## Alternative considerate

- **Altre regole sul testo** per ogni caso: è ciò che ha prodotto i sei criteri diversi.
- **La macchina che interpreta le frasi** (lessici del sì e del no): fragile su «Sì, però…», «Sì, non
  c'è problema»; viola il principio 10.
- **Tutto al modello senza stato esplicito**: il modello non può garantire che si esegua solo ciò che
  è stato proposto.
- **Un giudice separato per ogni risposta**: solo per le risposte ambigue a proposte di effetto E3–E4,
  in parallelo (~0,3 s).
- **Selezione dei tool per turno con un recupero semantico**: romperebbe la cache del prefisso;
  scartata a favore di pochi profili dallo stato (solo «sviluppo», da misurare).
- Da tenere d'occhio: la fine del turno decisa da un modello piccolo (*smart turn*), i modelli
  voce→voce in full duplex.

## Conseguenze

- Rischi dichiarati: un modello piccolo che non chiama il tool (c'è il ripiego sul comportamento di
  oggi); un dato non fidato che prova a «rispondere» alla proposta (il tool vale solo prima di un dato
  letto in quella risposta; attacchi nuovi nel banco); più attrito per le azioni E3 con la frase breve,
  da misurare in ombra.
- Decisioni sui punti aperti: la sfida resta legata al satellite; al più tre attese per persona; una
  proposta aperta si perde a un riavvio.
- Insieme al consenso unico arriva la tabella dichiarativa dei permessi ([0023](0023-tabella-dichiarativa-dei-permessi.md)).

## Fonti

- [`2026-10-10-macchina-stati.md`](../ricerche/2026-10-10-macchina-stati.md)
- [`2026-10-09-regole-incongruenze.md`](../ricerche/2026-10-09-regole-incongruenze.md)
