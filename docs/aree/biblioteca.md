# Biblioteca offline e ricerca web

*Wikipedia italiana e le altre fonti Kiwix in puro Python con FTS5; ricerca su internet con SearXNG. Documento d'area: nato il 06/10/2026 dividendo CLAUDE.md (proposta P7 di [`../ricerche/2026-10-06-analisi-complessiva.md`](../ricerche/2026-10-06-analisi-complessiva.md)). Chi lavora su quest'area aggiorna questo file; in CLAUDE.md al più una riga.*

## Moduli

| Stadio | Libreria | Dove |
|---|---|---|
| Biblioteca offline | Wikipedia italiana in ZIM di Kiwix, letta in puro Python (solo libreria standard, solo CPU) con un indice SQLite FTS5 accanto; niente `libzim` dal 01/10 | `calliope/biblioteca.py` → `Biblioteca.cerca`, `load_biblioteca`; `calliope/zim.py` → `ZimFile`; `calliope/biblioteca_indice.py` → `costruisci`, `apri`, `stato_indice`; tool `biblioteca_cerca`; file in `biblioteca/` (`scarica.sh`), indici in `biblioteca/indici/` |
| Ricerca su internet (facoltativa, solo con la rete) | SearXNG in un container di Calliope sulla DGX (`calliope-searxng`, 127.0.0.1:8004, niente log; `setup/linux/motore/searxng.sh`), httpx in POST; pagine con http.client e html.parser, senza SSRF | `calliope/web/` → `Web` (`servizio.py`), `Ripulitore` (`privacy.py`: niente dati personali nelle domande), `scarica`, `estrai_testo` (`pagina.py`), `load_web`; tool `web_cerca` in `calliope/tools/web.py`; `web_cerca` e `web_leggi` dell'agente in `calliope/agenti/ciclo.py`; solo letture dopo un risultato web: `politica.DOPO_DATO` (`politica.bloccata`) |

## Note dalla sezione «Stato attuale» di CLAUDE.md (fino al 06/10)

  - **Ricerca su internet quando c'è** (03/10, `calliope/web/`, rapporto
    [`docs/ricerche/2026-10-03-ricerca-web.md`](../ricerche/2026-10-03-ricerca-web.md)):
    `web_cerca` per l'attualità (meteo, notizie, risultati, orari, prezzi), la biblioteca resta
    la prima scelta per i fatti stabili; SearXNG sulla DGX (`calliope motore searxng avvia`,
    poi `web_searxng_url: http://127.0.0.1:8004` in `calliope.locale.yaml`); senza, il tool non
    c'è e la capacità «ricerca web» dice il passo. Livello minimo `web_livello` (familiare),
    `web_max_minuto` 10. Le domande escono senza nomi di casa, CF, IBAN, email, telefoni,
    `web_dati_privati` (regola `web_dati_tolti`) e non restano nel registro («******»). Il testo
    dei siti è non fidato: avviso, testo ripulito, **nessuna azione nella stessa risposta**
    dopo un risultato web (`web_azione_bloccata`) e fuori dalla storia a risposta finita;
    estratti con una data vecchia in fondo con «vecchio» (il 03/10 gemma4 diceva come domani il
    meteo di gennaio 2025). Agente: `web_leggi` solo sui risultati del suo lavoro, niente IP
    privati né nomi locali (SSRF), internet spento dopo i documenti di casa. Con Ollama (2
    giri): attualità 10/10, fatti stabili alla biblioteca 12/12, iniezione 0 azioni provate su
    8. Vera sulla DGX: ricerca 0,6–3,1 s (mediana 1,3), prima frase 1,55 s con la frase d'attesa.

  - **Biblioteca offline** (26/09): Wikipedia italiana per i fatti precisi, con la fonte
    citata a voce. Dal 01/10 senza `libzim` (lettore ZIM in puro Python e indice SQLite
    FTS5, anche su Windows ARM) e con Wikiquote per le citazioni.

## Note dalla sezione «Problemi noti» di CLAUDE.md (fino al 06/10)

- **Biblioteca offline** (26/09, [`docs/ricerche/2026-09-26-biblioteca-prova.md`](../ricerche/2026-09-26-biblioteca-prova.md)).
  La ricerca è lessicale, su CPU, in ~30 ms (massimo ~110). Usa i titoli esatti presi dalla
  frase, le parole di attributo con i sinonimi delle infobox, l'infobox per le domande sui
  dati, la voce completa se nel mini manca il dato e le voci-elenco per i superlativi.
  Recall@3 50/56. Il rerank con bge-m3 non migliorava (stesso recall, +169 ms, +0,76 GB):
  scartato. End-to-end 59/61 contro 56/61 senza (il 02/10, con l'indice FTS5 e `opzioni`
  corretta: 58–59/61 contro 52–53/61); senza biblioteca il 4B sbaglia con
  sicurezza (Manzoni «1812», Tevere «430 km»). Costo: **+0,5 s sulla prima frase** delle
  domande sui fatti. Tre regole nate dagli errori:
  1. il prompt nomina `biblioteca_cerca` solo se il tool c'è (`Config.prompt_for`); con un
     tool nominato ma assente il modello rispondeva «non ho accesso» a tutto;
  2. nel confronto dei titoli la parte tra parentesi non conta, e per i superlativi valgono
     solo i passaggi con un primato nell'ambito chiesto; senza, «il lago più grande d'Italia
     è il lago di Vico, secondo Wikipedia»;
  3. `cosa_fare` dice di ignorare i passaggi fuori tema e di non citare Wikipedia quando la
     risposta viene dalla memoria del modello.
  Le tabelle delle voci (classifiche, elenchi) non si leggono.

- **Biblioteca senza libzim** (01/10, [`docs/ricerche/2026-10-01-biblioteca-senza-libzim.md`](../ricerche/2026-10-01-biblioteca-senza-libzim.md)).
  `libzim` non ha wheel `win_arm64` (né libzim, kiwix-serve o Kiwix Desktop per Windows ARM):
  la biblioteca ora non la usa più, su nessuna piattaforma.
  - **Lettore ZIM in puro Python** (`calliope/zim.py`, ~590 righe): `mmap`, `struct`, `lzma`,
    `compression.zstd` (con Python < 3.14 il pacchetto `zstandard`, provato). Stesse voci e
    stesso HTML di libzim su 600 voci a caso dei 4 file (600/600,
    `prove/arm/confronta_lettore.py corretto`); apertura 0,2–0,5 ms contro ~100 ms; lettura
    di una voce 1,6–2,6 ms di mediana, p95 3–4 ms (decompressione a pezzi, cache di 8
    cluster); ~100 MB di memoria privata contro ~200. Thread-safe. Solo formato 6.x. Un file
    troncato o rovinato dà `ZimError`, non un crash.
  - **Indice SQLite FTS5** (`calliope/biblioteca_indice.py`) solo per Wikipedia ridotta e
    Vikidia: la completa si legge per titolo, il Wikizionario per percorso (indicizzarle non
    cambiava nessuna risposta). Parole ridotte con la stessa `_stem` del punteggio, alias
    dei redirect nel titolo, bm25 con peso del titolo 1 (`biblioteca_peso_titolo`).
    **`detail=full` è obbligatorio**: con `content=''` e `detail=column` bm25 vale sempre 0.
  - Costruzione misurata qui: mini **240 s con 4 processi, 1 308 MiB**, picco del processo
    principale ~1 GB (scansione 26 s); Vikidia 1 s, 10 MiB. Indice valido solo se completo,
    della stessa versione dell'estrattore (`VERSIONE` e firma di `_stem`) e dello stesso ZIM
    (uuid e dimensione); si scrive in `.tmp` e si rinomina. L'installazione lo costruisce
    dopo la verifica SHA-256, in un processo a parte a priorità bassa (`--stdin`: chiudendo
    lo stdin si ferma pulito). `risolvi_zim` passa a un file nuovo di quelle famiglie solo
    con il suo indice completo; la pulizia cancella anche gli indici dei file superati.
  - Qualità e tempi (`prove/prova_biblioteca.py`, stessa macchina e stessa ora): banco
    **49/56** (libzim 50/56: Colombo «1492» arriva dalla voce «America» solo con Xapian),
    banco nuovo da 46 domande **36/46** (uguale), altre prove 15/15; `cerca` mediana
    **28 ms**, p95 73, massimo 152, prima domanda 46 ms (libzim 41 / 116 / 406 ms, prima
    680 ms); apertura della biblioteca ~75 ms con gli indici. Full-text più lento di Xapian
    sulle parole frequenti (p95 36 ms contro 7), suggerimenti più veloci (p95 18 contro 40).
  - Su una macchina senza libzim (venv nudo, solo libreria standard) lettore, indice e banco
    danno gli stessi numeri. Da misurare sullo Spark: `prove/arm/` (vedi `prove/LEGGIMI.md`).
  - Con `processi` > 1 la costruzione usa `multiprocessing` «spawn»: va chiamata da un main
    protetto (`python -m calliope.biblioteca_indice`), mai da uno script senza
    `if __name__ == "__main__"` (i figli lo rieseguirebbero all'infinito).
  - **End-to-end con Ollama** (`prova_biblioteca.py --ollama`, stessa sera, stesso modello):
    nuovo 55/61 e 53/61 in due giri, HEAD con libzim 52/61. Il 59/61 del 26/09 non torna né
    con libzim né senza: colpa di `opzioni` (significati ambigui, 26/09), che prende la
    prima parola singola con una disambiguazione quando il modello riformula la domanda
    («caduta del **muro** di Berlino», «**profondità** del lago di Garda», «chi ha
    **composto** la Traviata», «**punto** più profondo», «**fine** della seconda guerra
    mondiale») e risponde «ha più significati». `Muro_di_Berlino` non si trova perché
    `exact` prova solo «Muro di berlino» e «Muro Di Berlino» (resta così: la ricerca la trova
    comunque).
  - **Corretto il 02/10** (`Biblioteca.opzioni`): la disambiguazione vale solo se la domanda è
    proprio su quel nome, cioè oltre al nome ci sono solo parole di richiesta o di attributo
    (`_NOT_SUBJECT`: «parlami di Venere», «cos'è un'iperbole?», «quanto è grande Venere?»).
    I 5 casi sopra non sono più ambigui (casi contrari in `prova_biblioteca`, altre prove
    22/22). End-to-end, 2 giri: **58/61 e 59/61** (manuale 41/43 e 43/43, difficili 17/18 e
    16/18), senza biblioteca 53/61 e 52/61; citazioni 3/4. Restano: «punto più profondo degli
    oceani» (risponde con l'abisso Vitjaz'), Colombo «1492», torre di Pisa, Kilimangiaro una
    volta senza tool. A secco invariato: banco 49/56, nuovo 36/46.
  - **Wikiquote nella ricerca** (prima fonte in più, `biblioteca_fonti_extra`, predefinita
    accesa): indice 144 MiB in 18 s; si apre solo con l'indice e si usa solo quando la
    domanda chiede una citazione (`biblioteca.RICHIESTE`: «citazione», «aforisma», «chi ha
    detto…», «proverbio»), con un vantaggio di +5 sul punteggio. Sulla voce dell'autore
    («una citazione di Einstein») il suo nome nel testo non conta: le righe che lo nominano
    sono frasi su di lui o fonti bibliografiche (`_NON_CITAZIONE`: traduzione, ISBN,
    editore e anno), e quelle con un'altra attribuzione in fondo («(Niels Bohr)») perdono.
    Con Wikiquote la descrizione di `biblioteca_cerca` nomina le citazioni e `opzioni` non
    si chiede. A secco 4/4, con Ollama 3/4 contro 0/4 senza (la «bellezza salverà il mondo»
    la attribuisce a un saggio omonimo); i banchi dei fatti non cambiano (49/56, 36/46).

- **Biblioteca: più fonti e significati ambigui** (26/09, `calliope/biblioteca.py`):
  - **Wikizionario** per «cosa significa…», «sinonimi/contrari di…» e «cos'è un…»
    (estrattore dedicato: sezione Italiano, definizioni per parte del discorso), 1–5 ms.
  - **Vikidia** con la precedenza per le spiegazioni semplici: profilo `giovane`
    (`arruola.py --giovane`) o richiesta «in modo semplice»; il tool chiede allora al
    modello parole adatte a un ragazzo.
  - **Ambiguità**: solo se la voce principale del nome è una disambiguazione per
    Wikipedia stessa (marcatore `mw:PageProp/disambiguation`: iperbole, Venere, Mercurio).
    Allora il tool dà 2–3 significati principali e il modello risponde sul più probabile e
    offre gli altri, o sceglie dal contesto. Quasi ogni nome ha una disambiguazione («Tevere»:
    fiume, dipartimento, nave…): se la voce principale è un articolo non si chiede nulla.
  - Le pagine di disambiguazione non si usano come passaggi. Limite noto: le domande con
    «perché» su fenomeni («perché piove?») trovano titoli omonimi (canzoni) invece della
    voce giusta.
