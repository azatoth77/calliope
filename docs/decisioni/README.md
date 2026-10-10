# Registro delle decisioni architetturali

Una decisione per file, in forma breve: contesto, decisione, alternative considerate, conseguenze,
stato e fonti. Il documento d'ingresso è [`docs/architettura.md`](../architettura.md); il metodo con
cui le decisioni nascono dai casi veri è in [`docs/analisi.md`](../analisi.md). I dettagli e le misure
stanno nei documenti d'area ([`docs/aree/`](../aree/)) e nelle ricerche ([`docs/ricerche/`](../ricerche/)).

**Stati**: *accettata* (in vigore, con la data), *superata* (sostituita da un'altra, con la data e il
rimando), *proposta* (progettata, non ancora nel codice o in corso). Una decisione superata non si
cancella: si segna come tale.

| N. | Decisione | Stato |
|---|---|---|
| [0001](0001-tutto-in-locale.md) | Tutto in locale, niente cloud | accettata, 21/09/2026 |
| [0002](0002-llm-dietro-api-intercambiabile.md) | LLM dietro un'API intercambiabile (Ollama nativo, OpenAI come ripiego, `llm_profilo`) | accettata, 21/09; 24/09; 03/10 |
| [0003](0003-moduli-sostituibili.md) | Moduli sostituibili e dipendenze native minime | accettata, 21/09 |
| [0004](0004-configurazione-fuori-dal-codice.md) | Configurazione fuori dal codice (dataclass, YAML, file locale) | accettata, 26/09; 01/10 |
| [0005](0005-python.md) | Python come linguaggio (C#/.NET valutato e scartato) | accettata, 21/09; riconfermata 10/10 |
| [0006](0006-half-duplex-e-barge-in.md) | Half-duplex, con il barge-in sul nome | accettata, 26/09 |
| [0007](0007-streaming-e-latenza.md) | Streaming frase per frase e latenza come metrica | accettata; latenza accettata 09/10 |
| [0008](0008-regole-deterministiche-solo-in-forma-chiusa.md) | Regole deterministiche sul testo solo nei casi stretti | accettata, 01/10 |
| [0009](0009-tool-uguali-per-ogni-livello.md) | Gli stessi tool per ogni livello, il permesso nel codice | accettata, 03/10 (supera il 23/09) |
| [0010](0010-server-di-casa-e-satelliti.md) | Un server di casa (DGX Spark) e satelliti in rete | accettata, 02/10 |
| [0011](0011-modello-davanti-agenti-dietro.md) | Un modello veloce davanti, agenti dietro (senza framework, con l'arbitro) | accettata, 02/10 |
| [0012](0012-sandbox-docker.md) | Il codice dell'agente in una sandbox Docker | accettata, 03/10 |
| [0013](0013-estensioni-porta-stretta.md) | Estensioni con porta stretta e approvazione con la sfida | accettata, 04/10 |
| [0014](0014-politica-unica-dati-in-busta.md) | Una politica unica dei tool, con i dati non fidati in busta | accettata, 05/10 |
| [0015](0015-sicurezza-per-valore.md) | Sicurezza per valore ed effetto | accettata, accesa 09/10 |
| [0016](0016-modalita-sviluppo-con-collaudo.md) | Modalità sviluppo a fasi, con il collaudo prima dell'approvazione | accettata, 08/10 |
| [0017](0017-ricollaudo-e-sonde.md) | Ricollaudo alla consegna e sonde solo verso host noti | accettata, 08/10 |
| [0018](0018-errori-dei-tool-strutturati.md) | Errori dei tool strutturati per il dialogo tra modelli e codice | accettata, 09/10 |
| [0019](0019-ombra-prima-di-accendere.md) | In ombra prima di accendere (metodo) | accettata, 08/10 |
| [0020](0020-trascrizione-senza-correzione.md) | La trascrizione non si corregge alla cieca | accettata, 07/10 |
| [0021](0021-ricerca-web-searxng.md) | Ricerca web con un SearXNG locale | accettata, 03/10 |
| [0022](0022-macchina-a-stati-del-dialogo.md) | Lo stato del dialogo come macchina a stati, con l'interprete del modello | proposta, in corso (10/10) |
| [0023](0023-tabella-dichiarativa-dei-permessi.md) | Una tabella dichiarativa dei permessi | proposta (10/10) |
| [0024](0024-niente-internet-se-non-serve.md) | Niente internet quando se ne può fare a meno: il meteo di casa | accettata, 09/10 |
| [0025](0025-minori-due-cancelli.md) | Minori: un segnale di pericolo poco chiaro passa da due cancelli | accettata, 09/10 |
| [0026](0026-satelliti-esphome-senza-home-assistant.md) | I satelliti parlano direttamente con Calliope (API di ESPHome), Home Assistant solo per la casa | accettata, 10/10 |
| [0027](0027-conversazione-come-registro-di-eventi.md) | La conversazione come registro degli eventi: un registro per conversazione, il resto proiezioni | proposta (10/10) |

Una decisione nuova prende il numero successivo e segue lo stesso formato; quando ne supera una
vecchia, la vecchia cambia solo lo stato («superata il …, vedi NNNN»).
