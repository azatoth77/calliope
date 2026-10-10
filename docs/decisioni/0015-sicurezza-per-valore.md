# 0015. Sicurezza per valore ed effetto

- **Stato**: accettata; fasi 1–3 l'08/10/2026 (fase 3 in ombra), **accesa il 09/10 sera** (fase 4)
- **Area**: [sicurezza-politica](../aree/sicurezza-politica.md)

## Contesto

La politica unica ([0014](0014-politica-unica-dati-in-busta.md)) decideva **per conversazione**: «c'è
di mezzo un dato non fidato, quindi chiedo». Il 07/10 sui registri della DGX: **15,8 domande ogni
100 turni**, e **28 su 41** (68 %) erano falsi positivi; nessun attacco vero. Un caso: 10 turni e quasi
due minuti per aprire un foglio Excel che Calliope aveva appena creato. Il problema non era il
determinismo ma la **granularità**: nessuna distinzione per argomento né per effetto, nessuna
memoria di ciò che la persona aveva già chiesto.

## Decisione

- **Provenienza per valore**: ogni argomento di un tool ha un'etichetta (detto dalla persona, della
  persona, fidato, scelta da un elenco, del modello, dal dato) e un tipo (bersaglio, contenuto,
  testo libero, scelta).
- **Classi d'effetto E0–E4**: lettura; locale e reversibile; persistente o condiviso; esce o esegue;
  fiducia e sicurezza fisica. Senza effetto dichiarato vale E3 (chiuso per difetto).
- Una **matrice** effetto × provenienza al posto di «pericolosa + contaminata ⇒ conferma».
- **Memoria dell'intento** (fase 2): ripetere la richiesta vale come sì, un «no» chiude la proposta,
  una domanda si fa una volta, 10 minuti di validità.
- **Attrito come metrica** (fase 1): `calliope stato --turni` lo conta, avviso oltre 3 domande ogni
  100 turni.
- Metodo: fase 3 **in ombra** per due giorni con un criterio scritto prima (nessuna esecuzione con un
  bersaglio preso dal dato, attrito simulato ≤ 3), poi accensione.

| Giorno | Turni | Attrito vero | Chiamate giudicate in ombra | Eseguite con bersaglio dal dato | Attrito simulato |
|---|---|---|---|---|---|
| 08/10 | 251 | 6,4 | 96 | **0** | **0,0** |
| 09/10 | 126 | 3,2 | 5 | **0** | **1,6** |

Accesa il 09/10 sera (`politica_per_valore` vero per difetto); la politica di prima resta **in ombra
al contrario** nel registro. Si spegne con `politica_per_valore: false` in `calliope.locale.yaml`.

## Alternative considerate

- **CaMeL** (un modello che pianifica e uno che legge i dati): il modello pianificatore da 4–26B è il
  punto debole e il costo in token (×2,8) è latenza; se ne prende l'idea delle capacità per valore.
- **MELON**, **code-then-execute**: una seconda passata a ogni tool, troppo per la voce.
- **Giudici LLM** per allargare i permessi: no; un giudice può solo stringere.
- **Copertura delle parole** della frase sul testo libero: chiederebbe sempre.

## Conseguenze

- Da guardare sulla DGX: «ESEGUITE con un bersaglio dal dato» deve restare 0.
- Le estensioni che leggono soltanto sono letture come la ricerca web (09/10).
- L'analisi delle regole del 09/10 ha trovato due regressioni della fase 4 (una sfida della classe
  persa), corrette la sera stessa; la sfida della classe è diventata un pavimento.
- La tabella dichiarativa dei permessi raccoglierà questa matrice ([0023](0023-tabella-dichiarativa-dei-permessi.md)).

## Fonti

- [`2026-10-07-sicurezza-per-valore.md`](../ricerche/2026-10-07-sicurezza-per-valore.md)
- [sicurezza-politica](../aree/sicurezza-politica.md), «Sicurezza per valore, fase 4»
- [`2026-10-09-regole-incongruenze.md`](../ricerche/2026-10-09-regole-incongruenze.md)
