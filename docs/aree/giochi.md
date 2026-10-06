# Giochi sugli schermi

*Schede interattive delle estensioni in un iframe isolato. Documento d'area: nato il 06/10/2026 dividendo CLAUDE.md (proposta P7 di [`../ricerche/2026-10-06-analisi-complessiva.md`](../ricerche/2026-10-06-analisi-complessiva.md)). Chi lavora su quest'area aggiorna questo file; in CLAUDE.md al più una riga.*

## Moduli

| Stadio | Libreria | Dove |
|---|---|---|
| Giochi e schede interattive delle estensioni (05/10) | JavaScript nel browser degli schermi in un `<iframe sandbox="allow-scripts">` (origine opaca, CSP senza rete, script con l'impronta), ponte `postMessage` controllato dalla pagina e dal server; test della logica con Node in un container (`Dockerfile.node`) | `calliope/estensioni/scheda.py` (sezione «scheda» del manifesto, gioco puro, `documento`, `RUNTIME_JS`, `analizza_js`); `calliope/schermi/giochi.py` → `Giochi` (partite, `GET /gioco/<gettone>`, `POST /api/gioco`), `AzioneGioco`; cane da guardia in `schermo.js`; `minori.TempoGioco`, `minori.Richieste`, tool `richiesta_tutore`; `calliope/agenti/test_js.mjs`; rapporto [`docs/ricerche/2026-10-05-giochi.md`](../ricerche/2026-10-05-giochi.md) |

## Note dalla sezione «Stato attuale» di CLAUDE.md (fino al 06/10)

- **Giochi sugli schermi** (05/10, [`docs/ricerche/2026-10-05-giochi.md`](../ricerche/2026-10-05-giochi.md)):
  un'estensione può avere una scheda interattiva (un gioco) che gira nel browser in un riquadro
  isolato (iframe sandbox senza `allow-same-origin`, CSP `connect-src 'none'`, runtime che toglie
  fetch/WebRTC/Worker, `frame-src 'self'` sulla pagina madre); messaggi solo con `calliope.*`
  (salva, leggi, manda, chat, di, azione), ricontrollati dal server; cane da guardia (ping,
  troppi messaggi, navigazione; dopo un ciclo infinito la pagina si ricarica: Edge riusava il
  processo bloccato). Gioco puro (niente permessi né azioni) → anche ospiti e schermi di
  stanza, approvato da un familiare adulto con la voce; partita condivisa tra schermi (con un
  minore o un ospite valori brevi e chat dal guardiano). Minori: tempo di gioco al giorno per
  fascia (`minori_gioco_minuti`), tempo in più da un adulto (scritto chi), richieste in attesa
  ai tutori («Intanto: Bianca ti ha chiesto…», `minore_gestisci approva_richiesta`, scadenza in
  3 giorni). Test dei giochi con Node nel container (`calliope motore sandbox costruisci
  javascript`). Prove: `prova_giochi` (banco d'attacco 17/17), `prova_giochi_pagina` (Edge:
  16 vie d'uscita bloccate, nessuna richiesta al server cattivo, tris tra due pagine).
  Agente vero sulla DGX (2 giri, 19 min): un memory puro pronto da approvare al primo giro, ma
  con un tocco che non funzionava → **prova di fumo** dei giochi (`agenti/fumo_js.mjs`: DOM
  finto e 300 tocchi a caso nei test); al secondo giro la prova ha trovato un `require` in
  gioco.js che l'agente non ha corretto in 24 passate (consegna e contratto ora lo spiegano;
  giro da rifare).
