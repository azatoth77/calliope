# 0012. Il codice dell'agente in una sandbox Docker

- **Stato**: accettata (03/10/2026)
- **Area**: [agenti-estensioni](../aree/agenti-estensioni.md), [sicurezza-politica](../aree/sicurezza-politica.md) (confine C3)

## Contesto

Gli agenti scrivono ed eseguono codice (Python, dal 04/10 anche C#) per i lavori che si chiedono a
voce. Fino al 03/10 il codice girava in un processo con un *audit hook* di Python, che la PEP 578
stessa non considera un confine di sicurezza.

## Decisione

- Ogni esecuzione in un **container usa-e-getta**: `--network none`, `--read-only`, `--cap-drop ALL`,
  `--pids-limit`, tetti di memoria e tempo; immagine Python da ~290 MB, una per C# con .NET e
  Roslyn senza SDK né NuGet.
- Costo misurato: **+0,12–0,18 s** per esecuzione rispetto al processo semplice. Accettabile.
- **Senza Docker il codice dell'agente non si esegue** (anche su Windows, dal 03/10).

## Alternative considerate

- **bubblewrap** e **`unshare -rn`**: non funzionano sulla DGX perché Ubuntu limita i namespace
  utente non privilegiati (`apparmor_restrict_unprivileged_userns`); servirebbe un profilo AppArmor
  con sudo o abbassare la restrizione per tutta la macchina. Scartati.
- **Audit hook di Python**: non è un confine.
- **gVisor** (`--runtime runsc`), uid dedicato, Docker rootless: passi possibili in futuro per
  rafforzare il confine, non fatti.

## Conseguenze

- Il confine è il **kernel condiviso**, non una macchina virtuale: un'evasione avrebbe i permessi
  di Calliope, e l'utente di Calliope nel gruppo `docker` vale root sull'host. È un problema aperto
  dichiarato in `CLAUDE.md` e nel README.
- Le estensioni usano lo stesso meccanismo, con in più una porta stretta ([0013](0013-estensioni-porta-stretta.md)).

## Fonti

- [`2026-10-03-sandbox.md`](../ricerche/2026-10-03-sandbox.md)
