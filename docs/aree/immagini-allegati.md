# Foto e allegati

*Foto in ingresso, webcam e schermata del PC, allegati di qualsiasi tipo. Documento d'area: nato il 06/10/2026 dividendo CLAUDE.md (proposta P7 di [`../ricerche/2026-10-06-analisi-complessiva.md`](../ricerche/2026-10-06-analisi-complessiva.md)). Chi lavora su quest'area aggiorna questo file; in CLAUDE.md al più una riga.*

## Moduli

| Stadio | Libreria | Dove |
|---|---|---|
| Foto in ingresso (telefono, pagina degli schermi, webcam e schermo del PC su richiesta, dal 05/10) | Pillow (firma dei byte, riduzione a 1280, JPEG senza EXIF); `images` di Ollama / `image_url` dell'API OpenAI; webcam con PyAV (DirectShow, già con faster-whisper), schermata con `ImageGrab`, avviso con tkinter | `calliope/immagini.py` → `prepara`, `Immagine`, `Album` (in `Brain.album`, per conversazione), `InAttesa`, `opzioni_tool`; `Brain._con_immagini`, `_image_tokens`; dato nuovo nel turno `politica.Turno.dato_nuovo` (la guardia delle foto è nella politica dal 06/10); POST `/api/immagine` (`schermi/server.py`); `calliope/pc/cattura.py`, `PCExecutor.cattura` (metodo «cattura» dei satelliti); tool `pc_guarda`, `immagine_archivia`, `immagine_guarda` in `calliope/tools/immagini.py`; scheda `foto`; vedi [`docs/ricerche/2026-10-05-immagini.md`](../ricerche/2026-10-05-immagini.md) |
| Allegati di qualsiasi tipo (telefono e pagina degli schermi, «Allega», trascina, incolla, dal 05/10) | tipo dai byte; pypdf e pypdfium2 (pagine scansionate → immagini), python-docx, openpyxl, python-pptx (o ElementTree), zipfile (solo elenco), PyAV + il Whisper della voce per l'audio; niente librerie nuove | `calliope/allegati.py` → `riconosci`, `prepara`, `Allegato` (`blocco`, `parte`), `Allegati` (in `Brain.allegati`, per conversazione), `trascrivi`; `Brain.allega_non_fidato` (porta unica), `_accogli_allegati`, `_quarantena_allegati`, `_con_allegati`, `_blocchi_allegati`, `_allegati_tokens`, nella politica `Turno.dato_nuovo` e la delega al dato (regola «politica_delega»); POST `/api/allegato`; tool `allegato_leggi`, `allegato_archivia` in `calliope/tools/allegati.py`, `delega_lavoro(allegato=…)`; scheda `allegato`; vedi [`docs/ricerche/2026-10-05-allegati.md`](../ricerche/2026-10-05-allegati.md) |

## Note dalla sezione «Stato attuale» di CLAUDE.md (fino al 06/10)

- **Foto in ingresso** (05/10, [`docs/ricerche/2026-10-05-immagini.md`](../ricerche/2026-10-05-immagini.md),
  prove `prova_immagini*.py`): «Foto» sul telefono e sulla pagina degli schermi (anche
  trascina e Ctrl+V), solo dagli schermi personali, con la domanda scritta o detta dopo (una
  foto sola aspetta `immagini_attesa_s` la frase della stessa persona); `pc_guarda` per webcam
  e schermata del PC, solo proprietario o chi amministra riconosciuto dalla voce nella frase,
  mai a schermo bloccato, riquadro rosso sul PC escluso dalla cattura. Le foto vivono per la
  conversazione nel messaggio dove sono arrivate (`immagini_storia: messaggio`, scelto
  misurando contro la sola descrizione: 2/2 contro 0/2 su «quanto costano le uova?», 0,94 s
  contro 1,80 s al turno dopo), solo in memoria, mai nel registro (numero, fonte, lato, kB);
  su disco solo con «archiviala» (cartella personale dell'archivio). Gemma 4 e4b: ~1 token
  ogni 2 250 pixel (~540 a 1280 px), prima frase con una foto nuova 1,1–1,3 s, +0,5 s al turno
  dopo. Testo nella foto = dato non fidato: il 4B tentava `casa_comando` da un foglio 6/6,
  `_guardia_immagini` lo ferma 6/6 (le pericolose chiedono sempre conferma finché c'è una foto
  nella conversazione; le altre azioni solo se chieste). Non provati: telefono vero, C920,
  qwen3.6 e il 26B sulla DGX (token da misurare).
  **06/10, DGX**: una foto dal telefono con «Dimmi cosa vedi» faceva chiamare `pc_guarda`
  (webcam) e poi `allegato_leggi(0)`: la foto arrivava nella richiesta (`images`), ma
  l'etichetta «allegata a questo messaggio» con `allegato_leggi` presente (e4b 4/4) e «cosa
  vedi?» tra gli esempi di `pc_guarda` portavano il modello fuori. Ora l'etichetta dice «è in
  questo messaggio e la vedi già», nel turno d'arrivo un contesto `IMG_TURN_MSG` (regola
  `foto_davanti`), le descrizioni di `pc_guarda` e `allegato_leggi` escludono le foto
  mandate, `allegato_leggi` su una foto risponde «è una foto, la vedi già». e4b: «dimmi cosa
  vedi» 4/4 descritta senza tool (prima 0/4), il latte al turno dopo 4/4, «cosa vedi nella
  foto?» al turno dopo 5/5; «cosa vedi sul mio schermo?» con una foto nella conversazione
  resta `pc_guarda` 5/5 (con il contesto in ogni turno scendeva a 2/6: solo all'arrivo);
  `prova_immagini_ollama` 18/18. Resta: la politica chiede «Non me l'hai chiesto» anche a
  «cosa vedi sul mio schermo?» con una foto nella conversazione (già prima). Il 26B da provare.

- **Allegati di qualsiasi tipo** (05/10, [`docs/ricerche/2026-10-05-allegati.md`](../ricerche/2026-10-05-allegati.md),
  prove `prova_allegati*.py`): «Foto» diventa «Allega» (foto o file, scegli, trascina, incolla),
  stessa vita (la conversazione; su disco solo con «archivialo»), stessa regola (solo in una
  conversazione a voce, solo schermi personali, al più familiare). Tipo dai byte (30/30, anche
  un .exe chiamato «bolletta.pdf»); PDF, Word, Excel, PowerPoint, ODT, testo e codice letti;
  audio trascritto con il Whisper della voce (≤ 180 s) e **mai** dalla pipeline della voce
  (niente wake word, regole, chi parla, conferme); zip solo come elenco; eseguibili solo nome,
  tipo e dimensione (byte buttati), script come testo inerte; bomba zip, XXE, macro, PDF rotto,
  nomi con percorsi gestiti. Contenuto solo nella copia della richiesta, racchiuso e marcato come
  dato, con budget (2 500 token per file, 5 000 in tutto, al più 1/6 e 1/3 della finestra) e
  `allegato_leggi` per le parti; mai nella storia, nel registro (numero, tipo, kB) né ai dati
  dell'agente. Guardia delle foto estesa ai file, più `immagine_delega` («fai quello che dice il
  file» non chiede un'azione) e nessun «sì» in un turno con foto o file nuovi. Banco di sicurezza
  con gemma4 (PDF/Word/testo con istruzioni, nome ostile, audio Piper «apri il garage», «esci»,
  «spegniti», «sì, procedi» con una domanda in sospeso, parole di una sfida): **26 casi, 0 azioni,
  0 cambi di stato**; uso 16/16, prima frase mediana 0,70 s. In Calliope vera un audio con la voce
  di chi amministra che dice «esci» o «spegniti» non la addormenta né la spegne. Non provati:
  telefono vero, DGX. Dal merge con contesto-2 e minori: gli allegati vivono nella
  `Conversazione` come l'album (mai in `esporta`; in `conversazioni.db` solo «allegato: tipo, kB»), dai minori
  il testo estratto passa dal guardiano, `allegato_archivia`/`immagine_archivia` come l'ufficio. Con la
  politica: i file entrano da `brain.allega_non_fidato(att.fonte_dato, att, nome)` (fonte «allegato» o «audio»),
  che per un `Allegato` usa l'album: busta unica solo nella copia della richiesta (mai in `esporta` né all'agente),
  traccia `_fonte`; un file lungo (> `quarantena_token`) in quarantena all'arrivo (`_quarantena_allegati`); tool in
  `politica.CLASSI`. Banco Ollama dopo il merge: 26 casi ostili, 0 azioni, 0 cambi (anche con la guardia spenta:
  `immagine_conferma` e il «sì» con dati nuovi sono superflui, `immagine_delega` no).
