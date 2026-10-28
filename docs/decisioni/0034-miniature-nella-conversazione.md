# 0034. Le foto si tengono 60 giorni, per sempre con «archiviala»

- **Stato**: accettata (28/10/2026, decisione di chi amministra, confermata dopo la domanda
  esplicita sulle catture di webcam e schermo e allargata la sera stessa alla foto intera), fatta il
  29/10 sul ramo `issue-272-miniatura-foto` (issue #272, PR #273). Cambia la regola «le foto solo in
  memoria, su disco solo con «archiviala»» (`calliope/immagini.py`, dal 05/10) e, per le foto, i 7
  giorni del cassetto (`cassetto_giorni`, dall'08/10).
- **Area**: [immagini-allegati](../aree/immagini-allegati.md), [schermi-telefono](../aree/schermi-telefono.md),
  [contesto-conversazione](../aree/contesto-conversazione.md); codice in `calliope/cassetto.py`
  (`metti_foto`, `stato_foto`, `dimentica_foto`), `calliope/tools/immagini.py` (`pc_guarda`,
  `immagine_archivia`), `calliope/schermi/schede.py` (`foto`, `per_conversazione`), `calliope/brain.py`
  (`manda_schede`, `_lega_in_attesa`); chiavi `immagini_tenuta`, `immagini_tenuta_giorni`

## Contesto

Fino al 28/10 una foto della conversazione viveva in memoria finché durava la conversazione; su
disco andava solo con «archiviala» (nei documenti di casa) o, se mandata da uno schermo personale,
nel cassetto per 7 giorni. Le catture di webcam e schermo (`pc_guarda`) non andavano mai su disco.
Con la Conversazione degli schermi (#242) la miniatura della foto doveva comparire accanto alla
frase della persona, e restare con il turno.

## Decisione

Testuale, di chi amministra (28/10): «tengo sempre la copia 60 giorni di default e la tengo per
SEMPRE se dico archiviala. Così uno ha tempo per pensare cosa fare»; e che si veda chiaramente quando
una foto è persa perché non è stata archiviata.

1. **Cosa si tiene**: la foto intera (il JPEG già ridotto, senza EXIF) nel cassetto della persona,
   e nel turno della Conversazione la sua miniatura di 144 px (dentro gli 8 kB della copia). Dei file
   allegati nel turno solo nome, tipo e dimensione.
2. **Per chi**: le persone di casa con l'identità certa, minori di famiglia compresi come gli adulti
   ([0031](0031-conservazione-dei-minori.md)); gli ospiti e la zona grigia mai. Una foto mandata da uno
   schermo personale è del suo proprietario; una cattura di `pc_guarda` di chi l'ha chiesta con la voce
   riconosciuta in quella frase.
3. **Per quanto**: `immagini_tenuta_giorni` (60) di serie, poi la foto si toglie dal disco; va via
   prima con «dimentica le nostre conversazioni» e con `calliope conserva --svuota`. Con
   `immagini_tenuta: false` le foto tornano come prima (il cassetto per `cassetto_giorni`, le catture
   solo in memoria).
4. **«archiviala» la tiene per sempre**, nei documenti personali dell'archivio di casa: anche una foto
   di giorni prima, finché la sua copia c'è («archivia la foto di martedì», `immagine_archivia` con
   `quale`). Solo con la voce riconosciuta o dallo schermo personale, anche sulla foto di questa
   conversazione (decisione di chi amministra del 29/10, dopo la seconda revisione della PR #273):
   dalla zona grigia, dalla frase breve o da un ospite il rifiuto generico del cassetto. **Cambia un
   comportamento in vigore dal 05/10**, quando «archiviala» sulla foto della conversazione bastava che
   ci fosse la persona della conversazione. Archiviata, la foto non scade più e non va via con «dimentica» (è stata tenuta di
   proposito); si toglie dall'archivio come gli altri documenti.
5. **Anche le catture di webcam e schermo**, sapendo che lì possono comparire schermate di posta e di
   documenti, dati di terzi, e i volti di ospiti e minori presenti nella stanza: il «mai degli ospiti»
   vale per chi parla, non per chi compare in una cattura. È una scelta di chi amministra, confermata
   dopo la domanda esplicita (revisione della PR #273).
6. **Lo stato si vede**: nel dettaglio della miniatura nella Conversazione una riga fra «La tengo fino
   al 27 dicembre: di' «archiviala» per tenerla sempre.», «Archiviata.» (con il rimando ai documenti) e
   «Non c'è più: non era stata archiviata.»; finché la foto c'è, il dettaglio mostra la foto intera,
   da «Scarica» (solo il proprietario, dal suo schermo personale, un gettone a tempo).
7. **Il modello vede come prima**: nella conversazione la foto resta nel suo messaggio
   (`immagini_storia`, `immagini_max_conversazione`); le copie e le miniature non gli arrivano.

## Alternative considerate

- **Solo la miniatura, catture comprese** (prima stesura della 0034, 28/10 pomeriggio): la
  Conversazione mostra che cosa si è visto, ma la foto si perde con la conversazione. Superata la sera
  stessa: serve tempo per decidere che cosa tenere.
- **Le catture come solo rimando** (proposta della revisione della PR #273): niente schermate né volti
  su disco. Scartata da chi amministra.
- **Tutto per sempre**: troppo, e contro la tenuta di 60 giorni degli altri dati
  ([0028](0028-decisioni-roadmap-12-10.md), T1).

## Conseguenze

- Le frasi «solo in memoria / mai su disco» di `immagini.py`, `tools/immagini.py`, `schede.foto` e
  delle voci d'area sono segnate come storiche col rimando qui.
- Il cassetto tiene le foto 60 giorni e gli altri file 7; la revisione del cassetto («scade tra poco:
  Tieni, Elimina») vale anche per le foto, verso la fine dei 60 giorni. «Elimina» del cassetto toglie la
  foto: nella Conversazione resta la miniatura del turno, con «Non c'è più: è stata eliminata dal
  cassetto.», fino ai 60 giorni del turno o a «dimentica».
- Le righe delle foto archiviate restano nell'indice del cassetto (pochi byte, senza file), perché la
  Conversazione dica «Archiviata.» anche dopo mesi.
- Il tetto per persona resta `cassetto_mb_persona` (oltre, la foto vive solo nella conversazione, e
  Calliope lo dice); una foto caricata resta sotto `immagini_max_mb`.
