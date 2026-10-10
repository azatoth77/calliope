# 0001. Tutto in locale, niente cloud

- **Stato**: accettata (21/09/2026), sempre in vigore
- **Principi**: 9 (niente cloud) di [`CLAUDE.md`](../../CLAUDE.md); requisito 3 della [visione](../visione.md)

## Contesto

Calliope è l'assistente vocale di una casa: sente le conversazioni della famiglia, riconosce le
voci, conosce i documenti personali e comanda luci e PC. Un servizio cloud vedrebbe tutto questo,
e smetterebbe di funzionare quando manca internet o quando il fornitore cambia condizioni.
Nella visione del 21/09 il requisito è netto: «Prima di tutto offline. … Voce, trascrizione e
LLM non vanno mai in cloud».

## Decisione

- Ogni modello gira su macchine di casa: VAD e wake word sui dispositivi, Whisper, LLM, chi
  parla e Piper sul server.
- Internet serve solo per **scaricare** modelli e pacchetti (sempre con conferma e SHA-256) e,
  se accesa, per la **ricerca web** con un SearXNG locale ([0021](0021-ricerca-web-searxng.md)).
- Ogni tool dichiara se richiede internet (`requires_internet`): senza rete sparisce dagli
  schemi e il resto continua a funzionare («degradare con grazia», principio 12 della visione).
- Da addormentata, nessun audio lascia il satellite: si trasmette solo dopo la wake word
  acustica (0 byte su una frase senza nome, misurato il 02/10).

## Alternative considerate

- **Servizi cloud per STT, LLM o TTS**: esclusi per principio (privacy, funzionamento senza rete).
- **Wake word commerciale con chiave API** (Porcupine): scartata perché dipende da un servizio
  remoto ([wake-word](../ricerche/2026-09-24-wake-word.md) §1).
- **Servizi esterni per ciò che si può fare in casa**: per esempio convertire le coordinate di
  Home Assistant in un nome di città con un servizio di geocodifica, scartato il 09/10
  ([0024](0024-niente-internet-se-non-serve.md)).

## Conseguenze

- La qualità è quella dei modelli che entrano in memoria: sul portatile da 8 GB di VRAM ci
  stanno un modello da ~4 GB e Whisper; sulla DGX modelli MoE più grandi
  ([0002](0002-llm-dietro-api-intercambiabile.md), [0011](0011-modello-davanti-agenti-dietro.md)).
- I fatti non stanno nel modello ma in una **biblioteca offline** (Wikipedia e altre fonti in
  formato ZIM), perché i modelli piccoli inventano ([biblioteca](../aree/biblioteca.md)).
- Le dipendenze vanno scelte guardando anche Windows su ARM ([0003](0003-moduli-sostituibili.md),
  [0005](0005-python.md)).
- I dati restano sul disco del server: memoria, registro dei turni, conversazioni. La loro
  protezione è un problema locale (permessi dei file, livelli delle persone).

## Fonti

- [`docs/visione.md`](../visione.md), «Requisiti» e «Principi: cosa cambia rispetto a CLAUDE.md»
- [`2026-09-24-wake-word.md`](../ricerche/2026-09-24-wake-word.md)
- [`2026-10-02-satellite.md`](../ricerche/2026-10-02-satellite.md) § 1
- [`2026-10-03-ricerca-web.md`](../ricerche/2026-10-03-ricerca-web.md)
