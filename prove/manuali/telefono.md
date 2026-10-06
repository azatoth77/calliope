# Prove manuali del telefono

*Passi spostati da `prove/LEGGIMI.md` il 06/10/2026. I comandi si lanciano dalla radice del repository.*

## Prova manuale del telefono (web app, 03/10)

La pagina `/telefono` fa del telefono un satellite: microfono, wake word «Calliope» e voce, nel
browser (`docs/ricerche/2026-10-03-webapp-telefono.md`). Serve Calliope sul server
(`audio_modo: satellite`) con la pagina degli schermi in rete (`schermi_indirizzo: 0.0.0.0`).

Sulla DGX, una volta (`ssh dgx`):

```sh
calliope stato --installa telefono      # onnxruntime-web (~14 MB) e i modelli generici della wake word
calliope schermi --certificato --host <IP della DGX in VPN>   # CA di casa + certificato della pagina;
                                        # aggiungi --host anche per l'IP di casa; stampa l'impronta della CA
calliope riavvia && calliope log        # «schermi: … pagina su https://<IP>:8770»
```

Il classificatore «Calliope» non si scarica (è addestrato qui): se `calliope stato` o la pagina
dicono che manca, copiarlo dal portatile:
`scp wakeword\modelli\calliope.onnx dgx:~/calliope/wakeword/modelli/`.
Firewall: come per il satellite, la porta 8770 solo verso la rete della VPN.

Sul telefono, in VPN:

1. **Certificato** (una volta). Aprire `https://<IP della DGX>:8770/telefono`, superare l'avviso
   (Avanzate → Continua) e toccare «certificato» in fondo alla pagina.
   - iPhone: «Consenti» il profilo → Impostazioni → Profilo scaricato → Installa; poi
     Impostazioni → Generali → Info → Impostazioni certificati attendibili → accendere
     «Calliope CA di casa». Confrontare l'impronta SHA-256 con quella stampata da
     `calliope schermi --certificato`.
   - Android: Impostazioni → Sicurezza → Crittografia e credenziali → Installa un
     certificato → Certificato CA → il file scaricato.
   Riaprire la pagina: niente più avviso (senza la CA la pagina funziona lo stesso, ma Chrome
   non registra il service worker e iOS può dimenticare l'eccezione nella web app).
2. **Abbinare**. Scrivere il proprio nome e «Chiedi il codice»: compaiono 6 cifre e il comando.
   Sulla DGX: `calliope satellite --abbina <codice> --stanza telefono --personale <nome>`
   (con `--personale` le schede personali vanno anche al telefono). La pagina passa da sola a
   «collegata» e prepara la wake word (~1–2 s la prima volta, 8 MB da scaricare).
3. **Aggiungere alla Home**: iPhone, Safari → Condividi → «Aggiungi alla schermata Home»;
   Android, Chrome → ⋮ → «Installa app» (o «Aggiungi a schermata Home»). Aprirla dall'icona:
   deve partire a tutto schermo e già abbinata (su iOS la web app ha un suo spazio: se chiede di
   nuovo il codice, abbinarla da lì).
4. **Parla**: toccare «Parla» e dire «che ore sono?» (senza il nome): risposta dal telefono.
   Tenere premuto e parlare a lungo: lasciando, la frase finisce.
5. **Microfono acceso**: accendere l'interruttore (la pagina chiede di tenere acceso lo schermo:
   se compare l'avviso «non tiene acceso lo schermo», allungare lo spegnimento automatico).
   Una frase senza il nome non deve far comparire nulla nel log della DGX; «Calliope, che ore
   sono?» sì. Mentre racconta una storia, «Calliope, basta» la ferma subito.
6. **Portatile e telefono insieme**: con il satellite del portatile collegato, finché il
   telefono non tocca «Parla» o accende il microfono ascolta il portatile (la pagina dice
   «In ascolto su «studio»»); dopo, il telefono; spegnendo il microfono (o bloccando il telefono) il
   posto torna al portatile (`[SATELLITE] attivo ora: …` nel log). Volume e file restano del
   portatile.
7. **Telefono bloccato o altra app**: il microfono si spegne (lo fanno tutti i browser) e la
   pagina, riaperta, lo dice.
8. **In auto** (CarPlay o Android Auto collegati, web app aperta in primo piano sul telefono):
   - l'audio di Calliope deve uscire dalle casse dell'auto; annotare se esce invece dal
     telefono;
   - provare «Parla» e il microfono acceso con il **microfono dell'auto** (di solito, con
     CarPlay o Android Auto attivi, il sistema usa quello) e poi con l'auto spenta e il telefono
     in mano: annotare quale microfono sente meglio il nome, i falsi risvegli con la radio
     accesa e se la riproduzione si interrompe quando parte il microfono (su iOS il passaggio
     tra «solo ascolto» e «ascolto e registrazione» può cambiare l'uscita: la pagina usa
     l'Audio Session API di Safari 17 se c'è);
   - con lo schermo del telefono acceso (wake lock) in un supporto: pulsante e stato si leggono
     a colpo d'occhio? I tocchi vanno fatti solo da fermi.
   Da annotare in `docs/ricerche/2026-10-03-webapp-telefono.md`.
9. **Schermo acceso** (04/10, `schermo-acceso.js`; prima di tutto annotare la versione di iOS,
   Impostazioni → Generali → Info). Blocco automatico a 30 secondi (Impostazioni → Schermo e
   luminosità), così la prova è breve; da ripetere in Edge nel browser e nella web app sulla
   schermata Home:
   - toccare «Microfono»: diventa «acceso», «Parla» si abbassa e nelle impostazioni (icona in
     alto a destra) c'è «Schermo acceso» (punto verde). Lasciare il telefono fermo **2 minuti**
     senza toccarlo: lo schermo non deve spegnersi né scurirsi. Dire «Calliope, che ore
     sono?»: risposta, e il testo nel carosello;
   - se invece compare «Lo schermo può spegnersi, e allora Calliope smetterà di ascoltare…»,
     annotare il testo intero (dice il perché: iOS prima della 18.4, risparmio energetico…);
   - con iOS dal 16.4 al 18.3 nella web app sulla Home l'avviso c'è anche se il browser dice
     sì (WebKit bug 254545): verificare che lo schermo si spenga davvero dopo 30 s (se resta
     acceso, l'avviso è troppo prudente: dirlo);
   - **risparmio energetico** acceso (Centro di controllo): ripetere i 2 minuti e annotare se lo
     schermo resta acceso o compare l'avviso;
   - cambiare app e tornare: il microfono è spento (va riacceso con un tocco) e con lui torna
     «Schermo acceso»;
   - Impostazioni → spegnere «tengo acceso lo schermo»: l'avviso in alto deve dirlo, e
     dopo 30 s lo schermo si spegne e Calliope smette di ascoltare (comportamento voluto);
   - **in auto**, nel supporto, di notte: la pagina si legge senza abbagliare? «Parla» e
     «Microfono» si prendono al primo tocco (da fermi)? Consumo della batteria in 30 minuti di
     microfono acceso (percentuale prima e dopo) e temperatura del telefono;
   - **carosello** (04/10 sera): chiedere «aggiungi il latte alla lista della spesa», «metti un
     timer di 5 minuti», «quanto fa 17 per 6»: ogni scheda compare per prima e si vede subito; si
     scorre di lato col dito (si ferma su una scheda intera, i puntini seguono); scorrendo a mano
     una scheda nuova non sposta la vista per una decina di secondi; il timer conta. «Scrivi»
     apre la casella con la tastiera; un modulo da compilare (`modello_compila` con dati
     mancanti) si apre da solo e la tastiera non copre «Invia».

### Il telefono si sente male: «Prova il microfono» (03/10)

Se Calliope dal telefono capisce parole senza senso (anche in altre lingue), risponde a frasi
mai dette («Grazie, grazie») o non riconosce la voce, sul telefono:

1. aprire la web app (aggiornata: chiuderla e riaprirla, o ricaricare la pagina) e, sotto il
   pulsante, toccare «Calliope non capisce bene? Prova il microfono» → «Prova il microfono»;
2. dire la frase che compare, due volte (5 s ciascuna: la seconda è senza le correzioni del
   browser), tenendo il telefono come quando si parla a Calliope;
3. sotto compare il riassunto: frequenze (microfono, contesto, riproduzione), durata vera
   contro durata dell'audio, livelli, secondi di voce per il VAD del server, tono della voce,
   impronta vocale contro quella del proprietario e, con ✗, cosa non torna. Mandare uno
   screenshot del riassunto (o il testo).

Serve un telefono **personale** (abbinato con `--personale`). Sul server le registrazioni
stanno in `<cartella di calliope.yaml>/diagnostica/telefono/<data>-<nome>/` (WAV del segnale
d'ingresso e dell'uscita a 16 kHz di ogni prova, `meta.json`, `riassunto.txt`), fuori da git,
per 7 giorni e al massimo 30 prove; la riga `[TELEFONO] prova del microfono …` nel log dice
quale. Per ascoltarle: `scp -r dgx:~/calliope/diagnostica/telefono/<cartella> .`

Cosa guardare: con l'audio giusto «durata» ha gli stessi secondi veri e di audio (ritmo ×1,000),
il tono di una voce adulta è tra ~85 e ~260 Hz e l'impronta del proprietario supera la soglia
(0,48). Un ritmo lontano da ×1, frequenze diverse tra microfono e contesto o un tono oltre i
300 Hz dicono che l'audio arriva accelerato o rallentato (il difetto di iOS del 03/10).

## Telefono da fuori casa (WireGuard e inoltro, 03/10)

I passi dipendono dalla rete di casa (VPN, router, indirizzi) e non sono pubblicati:
in breve, una VPN verso la rete di casa, `satellite_inoltro` sul satellite con le reti ammesse
in `satellite_inoltro_reti`, il certificato della pagina con gli indirizzi giusti
(`calliope schermi --certificato --host IP1,IP2`). Prova a secco: `prove/prova_inoltro.py`.
