# 0026. I satelliti parlano direttamente con Calliope (API di ESPHome), Home Assistant solo per la casa

- **Stato**: accettata (10/10/2026); chiude la decisione A di [`visione.md`](../visione.md), che era
  orientata verso «A+»
- **Area**: [satelliti](../aree/satelliti.md), [casa](../aree/casa.md)

## Contesto

La visione del 21/09 lasciava aperta la decisione A: Home Assistant come orchestratore della voce e
dei satelliti, con Calliope come cervello («A+»), oppure Calliope che parla direttamente ai satelliti
e usa Home Assistant solo per i dispositivi (B). L'analisi del 10/10 ha guardato i satelliti pronti
(Home Assistant Voice PE, schede ESP32-S3 con ESPHome, `linux-voice-assistant` per Raspberry): non
parlano Wyoming ma l'**API nativa di ESPHome** (protobuf su TCP, cifrata con Noise);
`wyoming-satellite` è archiviato dal 27/01/2026. Wyoming resta solo tra Home Assistant e i servizi
STT, TTS e wake word.

## Decisione

Decisione di chi amministra (10/10): **strada B**. Calliope parla ai satelliti con un adattatore
ESPHome (`aioesphomeapi`, MIT, solo sul server) dietro le interfacce dei satelliti remoti, con il
firmware originale. Home Assistant resta per luci, sensori e dispositivi di casa, fuori dal percorso
della voce.

## Alternative considerate

- **A+, Calliope dentro Home Assistant** (agente di conversazione compatibile OpenAI, STT e TTS come
  servizi Wyoming): lo STT di Home Assistant riceve solo la lingua, quindi niente «chi parla»; con
  l'agente OpenAI c'è lo streaming ma non il satellite, con l'agente Wyoming il contrario; il
  Raspberry di casa transcodificherebbe ogni risposta nel percorso critico. Resta possibile come
  compatibilità facoltativa.
- **Calliope server di `wyoming-satellite`**: progetto archiviato, satellite in chiaro e senza
  autenticazione.
- **Costruire da zero anche l'hardware** (la vecchia C): mai.

## Conseguenze

- Si conservano chi parla (due canali audio, quello ripulito e quello grezzo), lo streaming frase per
  frase, il follow-up, il barge-in col nome (l'eco la cancella il dispositivo), LED, volume, timer e
  annunci.
- Un dispositivo ha **un solo padrone per la voce**: Home Assistant o Calliope.
- È il server che si collega al dispositivo: finché la DGX resta in ufficio la prova si fa lì, e a
  casa servirà un ponte.
- L'API di ESPHome non è un contratto pubblico per server terzi: versioni della libreria e del
  firmware fissate insieme. La risposta audio passa in HTTP nella rete di casa, con indirizzi usa e
  getta.
- La wake word «Calliope» sul dispositivo richiede un modello microWakeWord e un firmware nostro: è
  un passo successivo.

## Fonti

- [`2026-10-10-wyoming.md`](../ricerche/2026-10-10-wyoming.md) (analisi, misura, piano a passi)
- [`2026-09-21-home-assistant-e-satelliti.md`](../ricerche/2026-09-21-home-assistant-e-satelliti.md)
- [satelliti](../aree/satelliti.md), voce del 10/10
