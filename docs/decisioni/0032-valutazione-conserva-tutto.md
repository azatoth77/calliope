# 0032. Durante la valutazione si conserva tutto, ospiti compresi, fino a una data

- **Stato**: accettata (18/10/2026, decisione di chi amministra), fatta il 18/10 sul ramo
  `issue-173-valutazione` (issue #173). È un'**eccezione a tempo** alla
  [0031](0031-conservazione-dei-minori.md) («degli ospiti mai») e alla
  [0029](0029-conversazione-di-stanza.md) (punto 1, «mai l'audio su disco», e punto 5, il testo
  della stanza solo della famiglia): vale solo fino alla data scritta nel file locale, poi tornano
  quelle.
- **Area**: [contesto-conversazione](../aree/contesto-conversazione.md),
  [stt-tts](../aree/stt-tts.md), [minori](../aree/minori.md); codice in `calliope/conserva.py`
  (`valutazione_attiva`, il solo posto che legge la data), `turnlog.py`, `stanza/tenuta.py`,
  `stanza/banco.py`, `stanza/lenta.py`, `conversazioni.py`

## Contesto

Le analisi dei casi veri si fermavano davanti ai buchi dei registri. Il 17/10 non c'erano né
l'audio né il testo per verificare due segnali del guardiano; il 18/10 le frasi non riconosciute in
auto erano «(una frase di un ospite)», senza parole né audio. Fino al 18/10 si conservavano: il
testo dei turni delle sole persone di casa riconosciute, l'audio dei turni sopra soglia e col
consenso, il testo della stanza della sola famiglia (`stanza_tenuta`), l'audio dei segmenti con
sole voci di casa (`stanza_audio_banco_giorni`), le conversazioni delle persone di casa
nell'archivio. Nessun interruttore conservava tutto.

## Decisione

Testuale, di chi amministra (18/10): «se rincorriamo i problemi con vincoli che ci mettiamo da soli
non andiamo da nessuna parte»; durante la valutazione tutte le conversazioni restano nei registri,
testo e audio.

1. **Un interruttore solo**: `conserva_valutazione_fino: "AAAA-MM-GG"` nel file locale (sezione
   `registro`, o fuori sezione). Vuoto, di serie, è spento. Vale **fino a quella data compresa**;
   una data scritta male è rifiutata con un avviso e resta spento.
2. **Il testo dei turni per tutti**: ospiti, zona grigia, voci sconosciute e conoscenti, con il
   livello e il «chi» come prima. Il turno porta il segno `conserva: {testo: true, motivo:
   valutazione, di_serie: <il motivo per cui di serie non sarebbe restato>}`.
3. **L'audio di ogni frase del turno**, qualunque sia la soglia della voce o il consenso, nello
   stesso formato (G.711 μ-law), in `turn_log_dir/voce/_valutazione/<id della persona o
   «ospiti»>/<giorno>/<ora>.wav`: le frasi che la regola di sempre tiene restano dove sono. Il
   tetto `conserva_voce_mb` vale per tutta la cartella, con la riga nel log quando lo si
   raggiunge.
4. **Il testo della stanza per tutte le voci** nella tenuta (`stanza_tenuta`), con `sicurezza:
   valutazione`: la ricerca (`stanza_cerca`), i nomi, la guardia e la ripresa dopo un riavvio
   leggono solo le righe di sempre, quindi quello che Calliope sa e dice non cambia.
5. **L'audio di tutti i segmenti della stanza** nel banco (`stanza_lenta`), non solo quelli con
   sole voci di casa: ospiti, conoscenti, zona grigia, «più voci», TV, allucinazioni, le frasi dette
   mentre Calliope parla; con `"valutazione": true` nel `.json`. Non dipende da
   `stanza_audio_banco_giorni` e non tocca `acceso.json`.
6. **Le conversazioni degli ospiti nell'archivio** su disco, con `ospite = 2`: nessuna ricerca,
   scheda «Conversazione», ripresa o riga «l'ultima volta…» le legge; l'archivio della sessione in
   memoria resta com'era.
7. **Valgono sempre**: `turn_log_days` (i file restano per quei giorni anche a valutazione
   finita), «dimentica» (il satellite per la stanza, la persona per le conversazioni),
   `calliope conserva --svuota` e `--persona` (anche sulle frasi della zona grigia attribuite a
   lei), la revoca del consenso alla voce (cancella anche le sue frasi della valutazione), la
   cancellazione di un profilo tolto. I dati restano sulla DGX, fuori da git, con i permessi
   privati di sempre (file 600, cartelle 700).
8. **Restano fuori anche durante la valutazione**: la frase di sfida e i codici detti (l'audio
   servirebbe a ripeterli), lo scritto (non c'è audio), le frasi non rivolte a Calliope nei turni
   (le prende la stanza), la **pausa** della stanza («abbiamo ospiti»: chi è presente l'ha chiesta
   in quel momento), `conserva_voce: false` (il no di chi amministra a tutta la voce), il journal
   di systemd (le frasi degli ospiti restano mascherate: il journal non si svuota con `--svuota`).
9. **Si dice**: all'avvio una riga «Valutazione: si conserva tutto fino al … compreso», e lo
   dicono `calliope stato` e il cruscotto di chi amministra; alla scadenza Calliope smette da sola
   e lo scrive nel log, una volta.

## Alternative considerate

- **Accendere solo la parte che serve a un'analisi** (il testo degli ospiti, poi l'audio…):
  scartata da chi amministra, è il «rincorrere i problemi».
- **Un interruttore per ognuna delle cinque cose**: scartato; una data sola si spegne da sé.
- **Le righe della stanza degli ospiti visibili alla ricerca**: scartato; cambierebbe ciò che
  Calliope dice (e chi lo sente) invece di conservare soltanto.
- **Ignorare anche la pausa della stanza**: non chiesto; resta la scelta prudente (una riga nel
  codice, `Banco.salva`, se chi amministra la vuole diversa).

## Conseguenze

- **Riservatezza**: si conservano le voci e le parole di persone che non lo sanno. È consigliato
  dirlo agli ospiti; lo decide chi amministra.
- **Disco**: sulla DGX, con i numeri del 14–18/10, la voce dei turni era fra 0,7 e 9,1 MB al giorno
  e il banco fra 0,1 e 5,9 MB; con la valutazione il giorno più pieno (18/10) passa da ~15 a ~20
  MB, cioè ~1,2 GB in 60 giorni. Il tetto `conserva_voce_mb` (2000) vale per la voce dei turni;
  il banco ha solo la rotazione di `turn_log_days`.
- **Latenza**: nessuna scrittura nuova nel thread della voce; le stesse scritture di prima, con
  meno filtri (il turno a voce finita, la stanza nel suo thread e in quello della corsia lenta,
  l'archivio nel suo).
- **Limite**: l'audio della stanza arriva al banco dalla corsia lenta; un segmento che scade in
  RAM prima che la DGX sia libera (`stanza_audio_min`, misura «scaduto» in `calliope stato
  --turni`) non ha l'audio, solo la riga.
- Nessuna regola sul testo nuova (principio 10); le misure d'ombra che contano «ospiti mai su
  disco» restano vere a interruttore spento.

## Fonti

- Issue #173 (analisi con i punti del codice); casi del 17 e 18/10.
- [0028](0028-decisioni-roadmap-12-10.md) T1, [0029](0029-conversazione-di-stanza.md) punti 1 e 5
  ed eccezione dell'audio del banco, [0030](0030-conoscenti.md),
  [0031](0031-conservazione-dei-minori.md).
- Prova a secco `prove/prova_conserva_valutazione.py`.
