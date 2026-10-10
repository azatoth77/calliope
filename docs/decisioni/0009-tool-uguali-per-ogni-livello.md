# 0009. Gli stessi tool per ogni livello, il permesso nel codice

- **Stato**: accettata (03/10/2026); **supera** la proposta del 23/09 (tool filtrati per livello)
- **Area**: [voce-e-regole](../aree/voce-e-regole.md), [`architettura-tool.md`](../architettura-tool.md)

## Contesto

Calliope distingue tre livelli di persone: **ospite** (voce non riconosciuta), **familiare** e
**chi amministra**. La proposta del 23/09 era di non mostrare al modello i tool vietati a un
livello, così «nessuna frase furba» poteva farglieli usare. Ma con un elenco di tool per livello,
ogni volta che cambiava chi parla il prefisso del prompt cambiava, e Ollama doveva rileggere
~6000 token: +1,1–1,5 s col modello da 4B, +2 s col 26B.

## Decisione

- Dal 03/10 il modello vede **tutti gli schemi, uguali per ogni livello** (72 sulla DGX al 09/10,
  più `esercizi` solo con un minore in casa). Prompt di sistema e schemi formano un prefisso
  identico byte per byte per tutti (una prova a secco lo controlla).
- **Il permesso lo decide solo il codice**, a ogni esecuzione, in `ToolRegistry.call`: un tool non
  ammesso torna con `ok: false`, «NIENTE: l'azione NON è stata eseguita» e una frase pronta che il
  modello non può riformulare in «fatto».
- Ciò che dipende da chi parla (nome, ricordi, fatti della casa) va nei **dati del turno**, subito
  prima della domanda, mai nel prefisso.

## Alternative considerate

- **Tool filtrati per livello** (23/09–02/10): più «sicuro» in apparenza, ma nascondere non bastava
  comunque (il modello ripescava i nomi dei tool dalla storia), e costava 1–2 s a ogni cambio di
  persona. Superata: con il prefisso unico la prima frase al cambio di livello è scesa da 1,85 a
  0,63 s col 4B e da 2,47 a 0,79 s col 26B.
- **Pochi tool per livello** (5–10): la ricerca del 26/09 ha misurato che gemma4 sceglie bene
  anche con 40 tool piatti.
- **Profili di tool dallo stato del dialogo** (per esempio i tool della modalità sviluppo solo con
  uno sviluppo aperto): proposti il 10/10 come passo 4 della macchina a stati, da accendere solo se
  il turno dopo il cambio resta sotto 1,2 s ([0022](0022-macchina-a-stati-del-dialogo.md)).

## Conseguenze

- La sicurezza non dipende da ciò che il modello vede: è la base della politica unica
  ([0014](0014-politica-unica-dati-in-busta.md)).
- Ogni tool nuovo allunga il prefisso per tutti: i tool vanno tenuti pochi e semplici.

## Fonti

- [`architettura-tool.md`](../architettura-tool.md) § 4 e § 5
- [`2026-10-03-modello-davanti.md`](../ricerche/2026-10-03-modello-davanti.md)
- [`2026-09-26-tool-e-agenti.md`](../ricerche/2026-09-26-tool-e-agenti.md)
