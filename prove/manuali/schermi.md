# Prove manuali degli schermi e dello scritto

*Passi spostati da `prove/LEGGIMI.md` il 06/10/2026. I comandi si lanciano dalla radice del repository.*

## Prova manuale degli schermi (da fare a voce)

Pagina in HTTPS (02/10): sul server `schermi_indirizzo: 0.0.0.0` con il certificato
(`calliope satellite --certificato`); il riassunto dell'avvio deve dire `https://<IP>:8770`.
Senza certificato: «schermi da configurare» con il passo, e la porta 8770 chiusa. Dal
satellite la finestra di Edge si apre su `http://127.0.0.1:<porta del ponte>` e mostra
«collegato». Da un tablet `https://<IP>:8770`: avviso del certificato la prima volta
(Avanzate → Continua), poi il codice di abbinamento. A secco: `prova_schermi.py`
(https, rifiuto in rete senza certificato, ponte con impronta giusta e sbagliata, ponte con 12 flussi da 2 MB nei due versi e 40 scambi brevi insieme) e
`prova_schermi_pagina.py` (la pagina vera attraverso il ponte, `isSecureContext`).

Calliope accesa sul portatile, con i valori predefiniti (`schermi_enabled: true`,
`schermi_indirizzo: 127.0.0.1`, `schermi_porta: 8770`).

1. Avvio: `python -m calliope`. Nel riassunto deve comparire
   `schermi: Apri http://127.0.0.1:8770 sul browser di questo computer…` (da configurare) o
   `schermi: N schermi abbinati…` (attiva). `python -m calliope.stato` dice lo stesso.
2. Aprire `http://127.0.0.1:8770` in Edge o Chrome (meglio a schermo intero, F11): compare
   «Abbina questo schermo» con un codice di 6 cifre.
3. Dire «Calliope, abbina lo schermo 123 456 al soggiorno» (con le cifre vere). Risposta
   attesa: «Fatto: lo schermo del soggiorno è abbinato.»; entro 2 secondi la pagina passa
   all'orologio e in alto a destra dice «collegato». Da terminale, in alternativa:
   `python -m calliope.schermi --abbina 123456 --stanza soggiorno`.
4. «Calliope, aggiungi il latte alla lista della spesa» → la scheda «Lista della spesa» con
   il latte in evidenza, insieme alla risposta (non dopo).
5. «Calliope, metti un timer di 5 minuti» → la scheda «Timer» con il conto alla rovescia.
6. «Calliope, chi era Garibaldi?» (con la biblioteca installata) → la voce di Wikipedia con il
   passaggio usato in evidenza e il testo più lungo sotto.
7. Facoltativo: «mostramelo sullo schermo», «togli tutto dallo schermo», «fammi vedere i miei
   promemoria sullo schermo» (deve rispondere che è una cosa personale e non mostrarla sullo
   schermo del soggiorno), «quali schermi ci sono?», «scollega lo schermo del soggiorno»
   (la pagina torna al codice).
8. Ricaricare la pagina (F5): torna collegata da sola e ripropone le ultime schede in basso.
   Chiudere e riaprire Calliope con la pagina aperta: la pagina si ricollega da sola.

Per un kiosk vero con Edge (InPrivate, dimentica tutto a ogni avvio):
`python -m calliope.schermi --kiosk soggiorno` stampa una volta sola il comando
`msedge.exe --kiosk "http://127.0.0.1:8770/#t=…"` da mettere nel collegamento di avvio.

Controllo nel registro dei turni (`registro/AAAA-MM-GG.jsonl`): i tool con schede hanno
`"schede": [{"tipo": "lista", "visibilita": "casa", "schermi": 1, …}]`; nella frase
dell'abbinamento il codice è `******`.

## Prova manuale di «scrivere invece di parlare» (03/10)

Con uno schermo personale (quello del satellite reso personale, o il telefono abbinato con
`--personale`): in fondo alla pagina c'è la casella «Scrivi a Calliope invece di parlare…».
1. Scrivere «che ore sono?» → risponde a voce dal satellite; nel terminale «✍ Scritto dallo
   schermo…»; nel registro `canale: scritto`.
2. «Calliope, aggiungi in rubrica il cliente Verdi Srl, partita IVA 12345678904» → «… non
   torna. Me lo ridici, o lo scrivi sullo schermo?» e sulla pagina il modulo del contatto con la
   partita IVA in rosso; correggerla (l'errore sparisce mentre si scrive), «Invia» → «Grazie, ho
   aggiunto Verdi Srl alla rubrica…». Nel registro solo i nomi dei campi.
3. «Calliope, fammi una fattura» → il modulo con cliente e voci; rispondere invece a voce: il
   modulo diventa «Hai risposto a voce.».
4. Scrivere «scarica Vikidia» (da chi amministra) → «Me l'hai scritto, ma per installare
   qualcosa mi serve la tua voce…»: la richiesta va ripetuta a voce con una frase intera.
