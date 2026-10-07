# Minori

*Fasce d'età, preset, guardiano, compiti, avvisi ai tutori. Documento d'area: nato il 06/10/2026 dividendo CLAUDE.md (proposta P7 di [`../ricerche/2026-10-06-analisi-complessiva.md`](../ricerche/2026-10-06-analisi-complessiva.md)). Chi lavora su quest'area aggiorna questo file; in CLAUDE.md al più una riga.*

## Moduli

| Stadio | Libreria | Dove |
|---|---|---|
| Minori (fasce d'età, preset per fascia, permessi nel codice, orari, compiti, avvisi ai tutori; dal 05/10) | SQLite (stesso file della memoria: `minori_regole`, `avvisi_tutori`, `compiti_giorno`); guardiano Llama Guard 3 8B su Ollama + rilevatore di pericolo (gemma4 e4b, output strutturato) | `calliope/minori.py` → `fascia`, `preset`, `permesso` (da `ToolRegistry.call`), `dato_turno`, `fuori_orario`, `piu_protetto`, `Compiti`, `Avvisi`, `estensione_consentita`, `conversazioni_visibili_ai_tutori`; `calliope/guardiano.py` → `Guardiano`, `filtra` (in `main.py`), `correggi_storia`; tool `compiti_aiuto`, `minore_gestisci` (`calliope/tools/minori.py`); terminale `python -m calliope.minori`; banchi `prove/prova_minori_ollama.py`, `prove/misura_guardiano.py`; [`docs/ricerche/2026-10-05-minori.md`](../ricerche/2026-10-05-minori.md) |

## Note dalla sezione «Stato attuale» di CLAUDE.md (fino al 06/10)

- **Minori** (05/10, `calliope/minori.py`, `calliope/guardiano.py`, rapporto
  [`docs/ricerche/2026-10-05-minori.md`](../ricerche/2026-10-05-minori.md)): profilo con data di
  nascita e tutori (speakers.json versione 2; «giovane» migra a «ragazzi»), aggiunto solo da chi
  amministra con voce e frase di sfida (`registra_utente` ora solo `amministra`; `arruola.py
  --nascita --tutore`); fasce piccoli < 7, bambini 7–10, ragazzi 11–13, adolescenti 14–17 con un
  preset ritoccabile per persona (`minore_gestisci`, `python -m calliope.minori`), come dato del
  turno al modello e nel codice per i permessi; voce incerta = profilo più protetto; guardiano
  (Llama Guard 3 8B, 0 falsi su 33 frasi giuste, 12/14 vietate fermate) su domanda e frasi solo
  per minori e ospiti, rilevatore di pericolo (gemma4 e4b, 9/10, nessun falso) con protezione,
  19696 e avviso ai tutori; compiti guidati, soluzione dopo 5 errori con avviso vero. Banco: 26B
  sulla DGX 48/48, 4B 45/48 (il 4B non conta i tentativi dei compiti); prima frase dei minori
  sulla DGX 1,36–1,48 s contro 0,89 senza guardiano, adulti invariati.

## Guardiano che non tace (06/10, Q3 della seconda analisi)

Dalla seconda analisi ([`../ricerche/2026-10-06-analisi-2.md`](../ricerche/2026-10-06-analisi-2.md),
§ 3.2): se il rilevatore di pericolo scadeva e il guardiano rispondeva, la domanda valeva «ok» e
nel registro c'era solo il tempo di Llama Guard. Ora:

- `Giudizio.pericolo` e `pericolo_ms` (esito e tempo del rilevatore, `giudica_domanda`) vanno nel
  registro dei turni (`guardiano.domanda`, `pericolo`, `pericolo_ms`, `guasto`); spento per
  configurazione = nessun esito, non un guasto.
- Per un minore (con `guardiano_se_guasto: blocca`) un guardiano **o** un rilevatore guasto o
  scaduto sulla domanda vale «guasto»: la frase di guasto, non la risposta (`filtra`,
  `Giudizio.guasto`). Gli ospiti passano come prima.
- Per un minore le schede della prima passata (biblioteca, web…) aspettano il giudizio sulla
  domanda (`Brain.trattieni_schede`, `rilascia_schede`, `filtra(al_giudizio=…)`): con «ok»
  partono, con pericolo o guasto mai (regola `schede_trattenute_scartate`). Costo: la scheda
  parte quando arriva il giudizio, che corre in parallelo con la risposta (prova: 201 ms dopo
  con un giudizio finto da 200 ms; sulla DGX `domanda_ms` è ~0,15–0,3 s); l'attesa vera va nel
  registro (`guardiano.schede_attesa_ms`). La voce non cambia.
- `calliope stato --turni` conta i giudizi mancati e avvisa anche con un solo turno
  (`latenza.avviso_guasti`, anche all'avvio).
- Il guardiano si carica all'avvio anche quando giudica gli ospiti (`guardiano_ospiti`), non solo
  con un minore in casa.

Prove in `prove/prova_minori.py` (rilevatore guasto, scaduto, spento; ospite; schede trattenute
e scartate; conteggio dei guasti).

## Permessi chiesti e richieste sentite (06/10, prova e2e)

Col 26B «posso giocare mezz'ora in più?» andava 2 volte su 3 a `minore_gestisci` (rifiuto)
invece che a `richiesta_tutore`, e «Sofia mi ha chiesto qualcosa?» del tutore non chiamava mai
`minore_gestisci(richieste)`. Ora `minore_gestisci` chiamato da un ragazzo per sé con
`tempo_extra`, `autorizza`, `abilita_estensione` o `orari` crea la richiesta al tutore (regola
`minore_gestisci_richiesta`); le descrizioni dicono che `minore_gestisci` è per gli adulti e che
«X mi ha chiesto qualcosa?» è `richieste`. Banco `prova_minori_ollama --gruppi richieste`
(gemma4 e4b, 3 giri): 9/12 → 12/12 (il tutore 0/3 → 3/3), prima frase 0,46–0,59 s. Da
riprovare col 26B.

**Giro 5 della prova e2e (06/10).** A «Sofia mi ha chiesto qualcosa?» la richiesta si diceva due
volte nello stesso turno (la frase di `minore_gestisci(richieste)` e poi «Intanto: …»), e dopo una
risposta che chiedeva qualcosa («Non sono sicura di aver capito… potresti spiegarmelo meglio?»,
a «spegniti» trascritto «spenniti») arrivava «Intanto: Sofia ti ha chiesto… Va bene?», che
diventava l'azione in sospeso del turno dopo. La regola `richiesta_al_tutore` è del tutore
adulto: nessuno stato dei minori era rimasto addosso ad Andrea. Ora `ciclo.richieste_al_tutore`
conta come dette le richieste elencate dal tool in quella risposta e aspetta dopo una risposta
che finisce con «?» (`Brain.ultima_domanda`). Prova in `prova_minori`.

## Pericolo con la frase spezzata (06/10, prova e2e, giro 0944)

Sofia: «un signore al parco mi ha detto di andare a casa sua» (pausa) «e di non dirlo alla
mamma». Il primo pezzo è diventato un turno con la protezione; il secondo, detto mentre Calliope
la diceva, l'ha interrotta con la sola voce (barge-in di livello B: Sofia è registrata) ed è
diventato un altro turno con un'altra protezione e un **secondo avviso «sicurezza»** ai tutori.
Corretto in `ciclo.py` e `minori.Avvisi` (prova `prova_minori_pericolo.py`, che fallisce sul
codice di prima):
- **Avviso una volta per episodio**: `Avvisi.manda(non_ripetere_s=…)` non riscrive lo stesso
  avviso (stesso minore, tipo e testo, cioè lo stesso argomento) entro
  `minori_avviso_ripetuto_s` (600 s; 0 = ogni volta), controllo e scrittura sotto lo stesso
  lucchetto; regola `avviso_pericolo_ripetuto`. Un argomento diverso («farsi del male» dopo «un
  signore») e un altro minore partono sempre: non si perde un avviso nuovo. La protezione a voce
  invece si dice ogni volta.
- **La protezione non si interrompe con la sola voce**: mentre suona (`protezione_in_corso`)
  `known_voice` risponde «continuo»; la ferma solo il nome («Calliope, basta», principio 8). Se
  il nome la interrompe prima della fine, si ripete **per intero** dopo la risposta del turno
  successivo della stessa persona entro 300 s (`protezione_interrotta`, `protezione_ripetuta`),
  salvo che quel turno l'abbia già detta lui; un'altra persona nel mezzo non la sente.
- **Pezzi uniti per il giudizio**: un pezzo detto da un minore interrompendo la risposta al suo
  pezzo di prima (entro 30 s, `UNIONE_PEZZI_S`) si giudica unito a quello (guardiano e
  rilevatore, regola `guardia_pezzi_uniti`): la seconda metà da sola può non sembrare un
  pericolo. Al modello e nella storia resta il pezzo com'è. Contrari: un'altra persona, una frase
  non detta interrompendo, oltre 30 s.

## Studio e Kolibri (ricerca del 07/10, nessun codice)

[`../ricerche/2026-10-07-kolibri.md`](../ricerche/2026-10-07-kolibri.md): in italiano Kolibri ha
solo Khan Academy di matematica (298 esercizi, programma USA); contenuti nuovi solo da Kolibri
Studio online; API interne con sessione; niente riquadro. Proposta: esercizi **nativi** preparati
dall'agente (scheda dei giochi, risposte controllate sul server, compiti guidati, revisione di un
adulto), Kolibri solo come catalogo opzionale dopo una prova. Pilota e decisioni nel rapporto.

## Emozioni dalla voce nell'interrogazione (ricerca del 07/10, nessun codice)

[`../ricerche/2026-10-07-emozioni-voce.md`](../ricerche/2026-10-07-emozioni-voce.md): modelli aperti
in locale ci sono (emotion2vec+, audEERING dimensionale in ONNX), ma su parlato naturale, ragazzi e
italiano nessuno ha numeri buoni (parlato naturale 0,43 di macro-F1, bambini 0,45 di UAR); solo
l'attivazione (arousal) è misurabile, la «sicurezza» (dominanza) è la più debole. AI Act: vietato
negli istituti di istruzione, non a casa per scelta della famiglia (linee guida della Commissione,
§ 255), ma resta un sistema ad alto rischio (fuori dalla versione pubblicata); legge 132/2025: dai
14 anni decide il ragazzo. Proposta: prima solo misure oggettive rispetto al proprio solito più
«come ti sei sentito?»; parte emotiva solo dopo una prova chiusa sulle voci vere, solo arousal per
sessione, visibile al ragazzo e al tutore come andamento (variante «mista»), mai etichette né voti.

## Età e compleanno dal profilo (07/10, DGX 06/10 sera)

Un minore che chiedeva «Quanti anni ho?» si sentiva dire «oggi è il tuo compleanno» (data di oggi
passata come nascita). Ora la data di nascita è nei dati del turno di chi parla
(`minori.dato_nascita`), `data_calcola` ha `persona` e rifiuta la data di oggi come nascita;
età e compleanno di un altro solo a chi amministra e ai tutori (`nascita_riservata`), un minore
solo la propria. `elenca_utenti` dice `minorenne` e `impronta_voce`. Dettagli e misure in
[memoria-agenda-liste](memoria-agenda-liste.md); prova `prova_eta_utenti`.
