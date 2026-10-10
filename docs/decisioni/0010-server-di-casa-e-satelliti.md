# 0010. Un server di casa (DGX Spark) e satelliti in rete

- **Stato**: accettata; server + satelliti dalla visione del 21/09, DGX Spark come server principale
  dal 02/10/2026. La migrazione a RTX Spark (Windows su ARM) resta aperta
- **Area**: [setup-dgx](../aree/setup-dgx.md), [satelliti](../aree/satelliti.md),
  [schermi-telefono](../aree/schermi-telefono.md)

## Contesto

La visione del 21/09 descrive un **server di casa** sempre acceso a cui la famiglia parla da ogni
stanza, con microfoni e casse «satellite». Fino al 02/10 il portatile faceva da server e da primo
satellite. Il 02/10 è arrivata una DGX Spark (Ubuntu 24.04 aarch64, GPU Blackwell, ~119 GB di
memoria unificata): più memoria per modelli migliori e per gli agenti, ma un sistema diverso da
Windows. Requisiti di chi amministra: un comando per installare, uno per aggiornare, ritorno alla
versione di prima se l'aggiornamento non parte, dati fuori dalla cartella del codice.

## Decisione

- **Server su Linux**: git + `uv` (lock universale, `uv sync --frozen`) + servizio **systemd
  utente**. `calliope aggiorna` prepara la versione nuova accanto, la verifica, riavvia; se il
  servizio non arriva al READY=1 torna da solo alla precedente (`calliope torna`).
- **Satelliti** con un **WebSocket proprio** aperto dal satellite, audio PCM 16 kHz, TLS obbligatorio
  in rete con certificato autofirmato e impronta fissata, abbinamento a codice. VAD e wake word sul
  satellite: da addormentato non manda nulla. Satelliti di oggi: PC Windows (anche esecutore delle
  azioni sul PC) e **telefono** come PWA nel browser (VAD e wake word in onnxruntime-web).
- **Schermi** (PC, tablet, TV) come pagine kiosk servite da Calliope (Starlette, SSE), abbinati a
  voce.
- Dal 06/10 tutti i satelliti ascoltano insieme: un ciclo («corsia») per satellite e **una
  conversazione per persona** che la segue di stanza in stanza.

## Alternative considerate

- **Calliope in Docker/Compose**: audio fragile nel container, ritorno automatico da scrivere a mano,
  immagine da 1,5–2 GB. Docker resta per i server dei modelli e per la sandbox.
- **Pacchetto `.deb`/apt**: sudo a ogni aggiornamento, nessun ritorno automatico. **snap, AppImage,
  pipx**: confinamento che complica audio e file, AppImage senza aggiornamenti.
- **pip + venv**: niente lock nativo.
- **Wyoming** (Rhasspy/Home Assistant) come protocollo dei satelliti: nessuna sicurezza né la
  semantica che serve, `wyoming-satellite` archiviato; **API nativa ESPHome**: contratto di Home
  Assistant, non pubblico. **TCP grezzo**: rifarebbe ciò che websockets già dà. **Opus**: dipendenze
  native senza wheel ARM, e la compressione può peggiorare Whisper.
- **Home Assistant come pipeline voce** («A+» nella raccomandazione del 21/09): HA avrebbe gestito
  audio e satelliti e Calliope sarebbe stata solo il cervello; nei fatti si è scelto di tenere i
  satelliti in Calliope, per sicurezza, barge-in e identità di chi parla. HA resta l'integrazione
  della casa ([casa](../aree/casa.md)).
- **App nativa sul telefono**: scartata il 02/10 a favore di una PWA servita da Calliope; limite
  accettato: una pagina web non può ascoltare sempre in tasca.

## Conseguenze

- Misure dei satelliti: +30–93 ms con una VPN simulata, barge-in locale in 28–83 ms, 1,4 % di un
  core sul satellite, venv da ~120 MB.
- Il telefono richiede la CA di casa installata.
- Non provati sul vero: un PC Windows pulito come satellite, l'iPhone in auto, le misure su Windows
  ARM. Satelliti di stanza su Raspberry o ESP32 restano futuri, con un possibile adattatore
  Wyoming/ESPHome.

## Fonti

- [`2026-10-02-impacchettamento-dgx-linux.md`](../ricerche/2026-10-02-impacchettamento-dgx-linux.md) § 3
- [`2026-10-02-satellite.md`](../ricerche/2026-10-02-satellite.md)
- [`2026-10-03-webapp-telefono.md`](../ricerche/2026-10-03-webapp-telefono.md)
- [`2026-10-01-mappe-e-schermi.md`](../ricerche/2026-10-01-mappe-e-schermi.md) § 9
- [`2026-09-21-home-assistant-e-satelliti.md`](../ricerche/2026-09-21-home-assistant-e-satelliti.md)
- [`2026-10-06-conversazione-persona.md`](../ricerche/2026-10-06-conversazione-persona.md)
