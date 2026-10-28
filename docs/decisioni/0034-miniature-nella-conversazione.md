# 0034. Le miniature delle foto restano col turno nella Conversazione

- **Stato**: accettata (28/10/2026, decisione di chi amministra, confermata dopo la domanda
  esplicita sulle catture di webcam e schermo), fatta il 29/10 sul ramo `issue-272-miniatura-foto`
  (issue #272, PR #273). Cambia la regola «le foto solo in memoria, su disco solo con «archiviala»»
  di `calliope/immagini.py` per la **miniatura**: la foto vera resta in memoria come prima.
- **Area**: [schermi-telefono](../aree/schermi-telefono.md), [immagini-allegati](../aree/immagini-allegati.md),
  [contesto-conversazione](../aree/contesto-conversazione.md); codice in `calliope/schermi/schede.py`
  (`foto`, `per_conversazione`) e `calliope/brain.py` (`manda_schede`, `_lega_in_attesa`)

## Contesto

Dal 28/10 (#242) la Conversazione degli schermi personali mostra le schede dentro le risposte,
copiate nel turno archiviato. Le foto e i file ne restavano fuori: le loro miniature partono prima
che la frase della persona entri nella storia, e si legavano al turno di prima (revisione della PR
#271). Fino a qui una foto non andava mai su disco, tranne con «archiviala»; la miniatura dello
schermo stava solo nella cronologia in memoria degli schermi.

## Decisione

Di chi amministra (28/10): la miniatura della foto compare nella Conversazione accanto alla frase
della persona, e **tutte le miniature, comprese le catture di webcam e schermo, restano su disco 60
giorni insieme al turno**.

1. **Cosa si salva**: la miniatura di 144 px (JPEG, dentro gli 8 kB della copia di una scheda;
   oltre, il solo rimando senza i byte). Mai la foto, mai il file; dei file solo nome, tipo e
   dimensione.
2. **Per chi**: le persone di casa con l'identità certa (minori compresi, come la
   [0031](0031-conservazione-dei-minori.md)); ospiti e zona grigia mai. La miniatura si lega solo
   al turno della persona che l'ha mandata o chiesta, mai a un'altra.
3. **Per quanto**: come il turno, 60 giorni (`turn_log_days`); va via con «dimentica le nostre
   conversazioni» e con `calliope conserva --svuota`. Un turno riservato non la tiene.
4. **Anche le catture di webcam e schermo** (`pc_guarda`): lì possono comparire schermate di
   posta e documenti, e i volti di ospiti e minori presenti nella stanza. È una scelta di chi
   amministra, confermata dopo la domanda esplicita (revisione della PR #273).
5. **La foto vera resta in memoria**, come prima: nell'album della conversazione, per il modello
   (`immagini_storia`), e su disco solo con «archiviala» o nel cassetto (`cassetto_giorni`).

## Alternative considerate

- **Catture come solo rimando**, senza la miniatura (proposta della revisione della PR #273): niente
  schermate né volti su disco, ma la Conversazione non mostrerebbe che cosa ha visto Calliope.
  Scartata da chi amministra.
- **Miniature solo in memoria**: si perderebbero a ogni riavvio, e la Conversazione sarebbe diversa
  fra uno schermo e l'altro.

## Conseguenze

- `immagini.py`, `tools/immagini.py` e `schede.foto` dicono la regola nuova, e la vecchia è segnata
  come storica.
- «Elimina» del cassetto toglie il file, non la miniatura nel turno: quella resta fino ai 60 giorni o
  a «dimentica».
- Il «mai degli ospiti» vale per chi parla, non per chi compare in una cattura: un ospite ripreso
  dalla webcam resta nella miniatura del turno di chi l'ha chiesta.
