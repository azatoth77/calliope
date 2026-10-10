# La scelta dei tool come metrica e un banco con le frasi vere (proposta, 10/10/2026)

*Proposta nata da un ragionamento con chi amministra la sera del 10/10, dopo i giri sulla DGX. Da
fare dopo il passo 4 del registro degli eventi
([`2026-10-10-registro-eventi.md`](2026-10-10-registro-eventi.md)) e prima del passo 2 della
macchina a stati ([`2026-10-10-macchina-stati.md`](2026-10-10-macchina-stati.md)), perché i tool per
stato nascano già misurati.*

## Il problema

Nei giri del 10/10 quasi tutti i difetti veri sono stati **scelte di tool**, non di comprensione né
di voce:

- **tool inventati** dal 26B: `sviluppo_stato`, `sviluppo_ferma` (lo schema «famiglia_verbo» di
  `sviluppo_apri`/`sviluppo_collauda` lo porta a completare nomi che non esistono, mentre le azioni
  stanno in `sviluppo_passo(azione=…)`);
- **il tool sbagliato fra due veri**: `sviluppo_chiedi` per «chiudi tutti gli sviluppi»,
  `lavoro_stato` per lo stato degli sviluppi;
- **il tool giusto usato male**: la modifica dell'analisi (`sviluppo_passo analisi cambia`) al posto
  dell'apertura di un altro sviluppo;
- **un tool per una frase senza senso**: `anagrafica_cerca` per «C'è Locutti».

Per chi parla l'effetto è lo stesso di un'incomprensione. Intanto la superficie è grande: 76 schemi,
circa 12 900 dei ~15 100 token del contesto. E la qualità della scelta oggi non si misura: la si
scopre leggendo i registri.

## La proposta

1. **Metrica a ogni turno**, in `calliope stato --turni` accanto alla latenza: nomi inventati (quali e
   cosa si voleva, ricavato dalla correzione), tool corretti al giro dopo, giri di correzione
   esauriti, ripieghi («Non ci sono riuscita»), e la persona che ripete o riformula la richiesta
   subito dopo (il segnale più forte di una scelta sbagliata). Un avviso oltre una soglia.
2. **L'errore che insegna**: quando un nome inventato non si riconduce a uno vero, l'errore strutturato
   del dialogo dei tool propone la chiamata completa («forse volevi `sviluppo_passo` con
   azione=ferma; esempio: …»), non solo i nomi vicini.
3. **Un banco della scelta dei tool con le frasi vere.** Dal registro degli eventi (contesto, stato,
   frase, tool e argomenti, e se la scelta era giusta: confermata dall'esito o corretta dopo) si
   costruisce un insieme di casi «in questo contesto, questa frase → questo tool con questi
   argomenti», con le frasi di chi usa Calliope (privato, fuori dal repository; nel repository solo
   casi riscritti con nomi di fantasia). Ogni modifica a un nome, a una descrizione, a un profilo per
   stato o al modello si prova lì prima di installarla: «prima 87 % giuste, dopo 93 %».
4. **Ridurre la scelta, sui numeri**: i tool per stato della macchina, nomi coerenti (rendere veri i
   nomi che il modello inventa sempre, oppure togliere lo schema che lo inganna: lo decide il banco),
   descrizioni che non si confondono («chiedi» e «chiudi»).
5. **Il modello si sceglie sul banco** (26B, un altro, il 4B per un profilo leggero): confronto
   oggettivo con le stesse frasi.

**Da verificare dopo**: il decoding vincolato (il motore non può generare un nome fuori elenco;
vLLM ha la generazione guidata, per Ollama con le chiamate native va verificato sulle versioni
attuali). Vincola il nome, non la scelta: un modello forzato può scegliere male fra tool veri, e lo
nasconde.

## Intanto

Raccogliere dati con l'uso normale e con i giri: il registro degli eventi in ombra conserva già ogni
turno con il contesto. La correzione della forma dei nomi `sviluppo_<azione>` è in corso (ramo
`pomeriggio-correzioni`).
