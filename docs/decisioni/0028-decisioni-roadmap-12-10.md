# 0028. Decisioni sulla roadmap del 12/10: dati, memoria, profilo ridotto, posizione del server, musica e allarme

- **Stato**: accettata (12/10/2026, risposte di chi amministra alle 41 domande sulla roadmap); il
  punto 1 (T1) in parte superato il 13/10 per il solo testo della conversazione di stanza, vedi
  [0029](0029-conversazione-di-stanza.md)
- **Area**: trasversale; [capacita-installazioni](../aree/capacita-installazioni.md),
  [voce-e-regole](../aree/voce-e-regole.md), [contesto-conversazione](../aree/contesto-conversazione.md),
  [casa](../aree/casa.md), [satelliti](../aree/satelliti.md)

## Contesto

Il 12/10 tre revisioni di prontezza hanno letto la roadmap voce per voce (registro degli eventi e
dialogo; voce, casa e satelliti; studio, immagini, sicurezza ed estensioni) e ne sono uscite 41
domande con una proposta ciascuna. Molte voci erano ferme non per la tecnica ma per una scelta mai
scritta: quanto tenere i dati con cui si misura (gli eventi si cancellano dopo 7 giorni, l'audio non
si salva), quanta memoria della DGX può prendere ogni modello nuovo (i liberi sono scesi da 21 a
10,5 GB in tre giorni), se serve ancora una Calliope su una macchina da 8 GB, se la DGX deve arrivare
in casa, e se musica e allarme sono ancora requisiti. Questa decisione raccoglie le scelte che
valgono per più aree; quelle di una sola voce sono nella coda di [`roadmap.md`](../roadmap.md).

## Decisione

1. **Conservazione dei dati (T1).** I turni e l'audio dei **soli adulti** si conservano in privato
   (fuori da git) per **60 giorni**, per misurare e migliorare Calliope: banco dei tool, set di
   regressione, dizionario delle correzioni, taratura delle soglie. Di **minori e ospiti mai**. Un
   comando svuota tutto. Oggi niente di questo è nel codice: gli eventi ruotano a 7 giorni
   (`eventi_giorni`) e l'audio si salva solo per il debug.
2. **Un piano unico della memoria (T4).** Prima di aggiungere un modello sulla DGX (immagini,
   secondo parere per lo studio, giudice di sicurezza, revisione notturna) si scrive il suo posto in
   un budget unico, quello di `calliope stato --piano`. Un modello entra solo dentro il budget.
3. **Il profilo ridotto da 8 GB è un vincolo di progetto (V7, E11).** La proposta di toglierlo è
   stata **ribaltata**: Calliope deve poter girare anche in forma ridotta, senza tutte le funzioni,
   su un PC con 8 GB di VRAM; più memoria c'è, più funzioni si accendono. Quindi:
   - ogni funzione dichiara come si comporta nel profilo ridotto (c'è, c'è in forma minore, manca e
     Calliope lo dice);
   - reti di sicurezza e regole dipendono dal modello e si tarano **per profilo**: spegnere nel
     modello da 26B le reti mai scattate (E11, dal 20/10, dopo un rapporto degli scatti per rete e
     per profilo) non le spegne nel profilo ridotto;
   - per lo stesso motivo resta in roadmap l'isolamento della sandbox su Windows (S12: no alla
     proposta di toglierlo).
4. **Dove sta la DGX non conta (T3, V8).** In casa o in ufficio con la VPN cambia poco: niente
   aspetta che la DGX arrivi in casa. Le mappe si fanno con la DGX come server. Music Assistant gira
   in un **container apposta**, da mettere dove serve, con la posizione in configurazione. Il
   satellite su Raspberry senza PC resta in roadmap come satellite di stanza, e non dipende da dove
   sta la DGX.
5. **Musica sì, allarme senza data (T2, V9).** La musica è un requisito confermato («assolutamente
   sì»). L'allarme resta in roadmap senza data: inserire a voce si farà più avanti, e oggi Calliope lo
   legge soltanto. I satelliti ESPHome si integrano quando arrivano, anche questi senza data.

Si aggiungono due scelte di metodo: la visione smette di essere la bozza del 21/09 e la roadmap
perde le righe superate (T5); prima di scrivere codice si rileggono le ricerche nate prima delle
scelte di fondo, qualche ora ciascuna: secondo fattore, musica, mappe, porta delle estensioni,
immagini (T6).

**Proposta in valutazione, non decisa: un LLM nel cloud.** Chi amministra ha scritto che, al limite,
chi vuole potrebbe collegare un LLM nel cloud e usare sopra tutta l'impalcatura di Calliope, sempre
con l'obiettivo di tenere tutto offline. Non è una decisione: è in roadmap tra le cose «in
valutazione (non promesse)». Il backend compatibile OpenAI ([0002](0002-llm-dietro-api-intercambiabile.md))
basterebbe a collegarlo, ma non basta a deciderlo: servono analisi apposite sul principio 9 («niente
cloud») e sulla decisione [0001](0001-tutto-in-locale.md), sulla privacy dei dati che uscirebbero di
casa, sui minori, sui costi e su cosa resta comunque locale. Se un giorno si decide, servirà una
decisione propria.

## Alternative considerate

- **Togliere il profilo da 8 GB** e tenere il portatile solo come satellite: era la proposta (V7),
  scartata da chi amministra.
- **Aspettare la DGX in casa** per ponte verso casa, musica e mappe: era la proposta (T3), scartata.
- **Conservare tutto per tutti**, minori compresi: mai proposto; i minori restano fuori da ogni
  conservazione per misura.
- **Una regola rigida sulla configurazione** («un campo nuovo ne toglie uno»): scartata (E10); si fa
  un inventario una tantum dei campi mai cambiati, e quali diventano costanti lo decide chi
  amministra, perché tocca la personalizzazione.

## Conseguenze

- Il banco dei casi veri, la taratura delle soglie e la revisione notturna hanno ora una fonte di
  dati possibile: serve il codice della conservazione (cartella privata, durata, esclusione di
  minori e ospiti, comando per svuotare), e i dati restano fuori dal repository pubblico.
- `calliope stato --piano` diventa il posto dove si scrive il budget di memoria; immagini (circa
  16 GB stabili da liberare) e secondo parere con il modello dell'agente aspettano quel budget.
- Il profilo ridotto va progettato davvero: oggi in roadmap era una riga «non definita». Ogni lavoro
  nuovo dice cosa fa nel profilo ridotto; le prove col modello girano anche sul profilo piccolo.
- Musica e mappe non aspettano la DGX in casa; la musica si progetta dopo la rilettura della ricerca
  del 21/09, nata per un server Windows e per i satelliti di Home Assistant.
- L'allarme resta in sola lettura; nessun tool per disinserire, come scritto nella visione.

## Fonti

- [`roadmap.md`](../roadmap.md) (coda del 12/10 con la prontezza di ogni voce), [`visione.md`](../visione.md)
- [`2026-10-07-taratura-macchina.md`](../ricerche/2026-10-07-taratura-macchina.md) (piano dei modelli,
  classi di macchina)
- [`2026-09-21-musica-e-hardware-audio.md`](../ricerche/2026-09-21-musica-e-hardware-audio.md)
- [`2026-10-06-analisi-2.md`](../ricerche/2026-10-06-analisi-2.md) § 6 (Q12–Q14)
- Decisioni [0001](0001-tutto-in-locale.md), [0010](0010-server-di-casa-e-satelliti.md),
  [0026](0026-satelliti-esphome-senza-home-assistant.md)
