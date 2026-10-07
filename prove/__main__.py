"""
Tutte le prove in un comando: `python -m prove` (dalla radice del progetto).

    python -m prove              # livello 1 + livello 2 (legate ai file cambiati): ~30–90 s
    python -m prove --completo   # tutte le prove a secco: prima dell'unione su main
    python -m prove --ollama     # anche quelle con il modello vero (qualche minuto)
    python -m prove --help       # le altre opzioni (--hook, --staged, --ramo, -j, --timeout)

Ogni prova è uno script di prove/ che esce con 1 se qualcosa non va e con 77 se si salta
per intero (manca un browser, una voce, un modello…). Dal 06/10 (P5 dell'analisi
complessiva) a livelli: 1 le veloci, sempre, in parallelo; 2 quelle legate ai file cambiati
(LEGAMI), in parallelo; 3 lunghe, con il browser, con Calliope vera o in tempo reale, in
serie, solo con --completo. Ogni prova ha un tempo massimo (300 s) e gira in un job object
(Windows). L'hook (.githooks/pre-commit) lancia `--hook --staged`: livelli 1 e 2 sulla copia
dell'indice. Non tocca speakers.json, memoria.db né registro/: le prove usano file temporanei.
"""

import os
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

RADICE = Path(__file__).resolve().parent.parent

A_SECCO = [
    ("prova_testo.py", [], "wake word testuale, uscite, pulizia, frasi, calcola"),
    ("prova_runner.py", [], "il runner stesso (06/10, Q7): ogni prova registrata o manuale, legami dei tool d'area, salti parziali segnalati"),
    ("prova_dati_privati.py", [], "nessun dato privato nei file tracciati (06/10, pubblicazione): file vietati, segreti, IP privati non d'esempio, DuckDNS, percorsi utente, termini di privato/termini.txt"),
    ("prova_docs_aree.py", [], "documenti d'area (06/10, Q8): i nomi in backtick delle tabelle «Moduli» esistono nel codice"),
    ("prova_e2e_copioni.py", [], "prova end-to-end della DGX (prove/e2e/) a secco: copioni ben fatti, controllo dei passi, sfida, nessun dato personale"),
    ("prova_pronuncia.py", [], "pronuncia degli inglesismi (04/10): «file» → «fàil», contrari, solo il testo per Piper"),
    ("prova_personalita.py", [], "personalità (04/10): toni di voce, wake word cambiata e in testa alla frase, modalità startrek, suoni di ascolto"),
    ("prova_modalita.py", [], "modalità cambiata a voce (05/10): solo chi amministra dalla voce, subito e salvata, cosa è acceso davvero, satellite collegato aggiornato e modello mandato dal server, satellite vecchio, telefono, ritorno alla normale"),
    ("prova_tool.py", [], "tool nativi e permessi per livello"),
    ("prova_sicurezza.py", [], "sicurezza (analisi del 03/10): registrazione della voce, fatti della casa, sandbox, apri, permessi"),
    ("prova_politica.py", [], "politica unica dei tool (05/10): provenienza, dati non fidati in busta, classi, banco d'attacco da web, foto, allegati, estensioni, archivio, agenti"),
    ("prova_conferma_unica.py", [], "una conferma per azione (06/10, caso della DGX): «creiamo…» con una foto di mezzo, conferma della politica e «Procedo?» del tool fusi, sfida, doppioni di una funzione che c'è già, annuncio coerente con la dimostrazione"),
    ("prova_risultati.py", [], "risultati dei lavori e consensi (07/10, casi della DGX): risultato_lavoro (quale lavoro, riassunto salvato o dal modello dell'agente, tempo massimo, schermo, codice mai a voce, dopo un riavvio, permessi), dichiarazioni «inizio subito il lavoro», il «sì» di chi non ha la proposta, «Ma sì dai, perché no?» e i contrari; casi del 07/10 mattina: falso allarme di riferire su «installarlo», scheda del risultato nella zona grigia e dopo schermo_mostra, lavori_stato con i lavori finiti dal disco"),
    # ~8 s: FakeOllama, hub e server degli schermi veri su 127.0.0.1, satellite e PC finti
    ("prova_markdown.py", [], "Markdown dei testi dell'agente (07/10): blocchi, righe, voce, conversioni in PDF e Word veri e da blocchi, testi ostili (script, javascript:, tabelle enormi, annidamenti, enfasi senza chiusura) in poco tempo; risultato.md, annuncio, scheda del documento con «Scarica», risultato al portatile con «Lo apro?» o sul server; «Scarica» solo per lo schermo personale del proprietario, mai zona grigia né stanza, gettone che scade, Content-Disposition e CSP sandbox; «fammene un PDF»"),
    ("prova_conferme.py", [], "conferme (04/10): «sì» breve di chi amministra, proposta valida 3 turni, frase di sfida"),
    ("prova_voci_famiglia.py", [], "voci di famiglia (07/10): margine tra primo e secondo profilo, chi amministra con un minore vicino, la frase che chiede chi parla, conferma breve con un'altra voce più vicina, i quattro casi veri con impronte sintetiche"),
    ("prova_minori.py", [], "minori (05/10): fasce, preset e permessi nel codice, orari, voce incerta, compiti e avvisi ai tutori, guardiano finto, registrazione con la sfida, privacy"),
    ("prova_eta_utenti.py", [], "età e compleanni dai profili (07/10, DGX): data di oggi come nascita rifiutata, persona=io o un nome, giorni contati dal programma, privacy (chi amministra e i tutori), impronta della voce in elenca_utenti, rubrica distinta, tool *_cerca con argomenti obbligatori, parole di un ospite nel registro"),
    ("prova_minori_pericolo.py", [], "minore in pericolo con la frase spezzata (06/10, e2e): pezzi uniti per il guardiano, protezione senza barge-in con la sola voce e ripetuta se il nome la interrompe, avviso non ripetuto per lo stesso episodio, con i contrari"),
    ("prova_brain.py", [], "filtro del thinking, guardia, ciclo dei tool, storia"),
    ("prova_tempi.py", [], "durate e orari detti a voce"),
    ("prova_stt_correzione.py", [], "correzione delle frasi incerte (05/10, spenta): confidenza da verbose_json, controllo con i contrari, correttore finto, privacy; parole incerte al modello e frase capita trattenuta (07/10)"),
    ("prova_latenza.py", [], "latenza vera della voce (06/10, P2–P4, P11): guardiano e rilevatore caldi e ricaricati, domanda giudicata in parallelo, conversazione ripresa in cache, mediana e p90 per giorno con le cause e l'avviso, riassunto dell'agente con un tempo massimo; prima frase a pezzi, taratura della voce e dal testo alla voce (07/10)"),
    # ~9 s: microfono e VAD finti in tempo quasi reale, server dei satelliti vero, node se c'è
    ("prova_pause.py", [], "pause e fine del turno (07/10, solo misura): pause interne e parlato da Listener, satellite e telefono (voce.js con node), ripresa dopo la frase con i contrari (casse, risposta, oltre 2 s), «aspetta»/«non ho finito» con i contrari, campo «ascolto» del registro, frase_finita e «ripresa» nel protocollo (satellite vecchio), riassunto e soglia stimata in `calliope stato --turni --pause`"),
    ("prova_config.py", [], "calliope.yaml, variabili d'ambiente, chiavi sbagliate"),
    ("prova_config_satellite.py", [], "microfono, casse e webcam nella sezione satellite, ripiego con avviso"),
    ("prova_contesto.py", [], "finestra di contesto dal setup (modello, memoria, tempo) e token veri a ogni turno"),
    ("prova_conversazioni.py", [], "conversazione come oggetto, archivio delle conversazioni (ricerca ibrida, visibilità), compressione vicino al limite, fine e ripresa"),
    ("prova_ollama_carico.py", [], "modelli residenti in Ollama (06/10, e2e): limite letto o assunto, avviso quando Calliope ne usa di più, embedding delle conversazioni solo senza scacciare nessuno (inattiva, keep_alive 0, ricerca per parole con Ollama pieno)"),
    ("prova_corsie.py", [], "conversazioni per persona e satelliti insieme (06/10): scelta della conversazione, ospiti per satellite, «sì» breve altrove, doppioni, risposte in parallelo con la coda, smistatore, ciclo e stato della voce per corsia, ripresa"),
    ("prova_ciclo.py", [], "il ciclo della voce (06/10, P8) giro per giro con tutto finto: primo avvio e registrazione, nome vero, finestra di ascolto, approfondisci, ricerca promessa, ricominciamo, cortesia, frase ignorata, esci, spegniti"),
    ("prova_nome_da_solo.py", [], "il nome da solo e la modalità Star Trek in uso (06/10, DGX) con un satellite finto: scatto sicuro con testo vuoto o nome storpiato breve → saluto o suono d'inizio e finestra aperta, suono di fine se nessuno parla; contrari; tool senza argomenti obbligatori senza frase d'attesa; risposta di sola punteggiatura"),
    ("prova_agenda.py", ["--secco"], "timer, promemoria, appuntamenti: scadenza, annullo"),
    ("prova_memoria.py", ["--secco"], "memoria per persona"),
    ("prova_liste.py", [], "liste della casa e memoria della casa"),
    ("prova_pc.py", [], "tool pc_* con un PC finto: permessi, valori a voce, blocco"),
    ("prova_documenti.py", [], "documenti Word, Excel e PDF: file, formule, modifiche, permessi"),
    ("prova_ufficio.py", [], "ufficio: conti, XML FatturaPA (XSD se c'è), numerazione concorrente, rubrica, modelli Word e PowerPoint, flusso a voce"),
    ("prova_casa_ha.py", [], "casa via Home Assistant con un HA finto: regole, permessi, TLS, diagnosi"),
    ("prova_capacita.py", [], "registro delle capacità: stati, riassunto, prompt, calliope_stato, macchina nuova"),
    ("prova_installa.py", [], "installazioni con un server HTTP finto: catalogo, permessi, offerta, ripresa"),
    ("prova_schermi.py", [], "schermi: server e SSE veri, abbinamento, visibilità, schede dei tool, log"),
    # ~3 s: server degli schermi vero, registro dei turni finto (anche grande: 28 000 turni)
    ("prova_cruscotto.py", [], "cruscotto di chi amministra (06/10): solo lo schermo personale di chi amministra, nessun testo di persone, latenza, regole, errori, abbinamenti, richieste in attesa, cache e registro grande, prefisso del modello invariato"),
    # ~20 s: la pagina degli schermi e del telefono in Edge o Chromium senza finestra
    ("prova_cruscotto_pagina.py", [], "cruscotto nella pagina vera: pulsante solo per chi amministra, scheda con le sezioni, Aggiorna al suo posto, Chiudi, nel carosello del telefono dal menu, nessun errore JS"),
    # ~25 s: la pagina del telefono e dello schermo in Edge o Chromium senza finestra
    ("prova_markdown_pagina.py", [], "lettore Markdown nel browser vero (07/10): testo dell'agente ostile (script, HTML con attributi, javascript:, immagini) mai eseguito né come elementi, tabella di 300 righe, annidamenti, sommario, «Scarica» PDF/Word/MD negli scaricamenti, schermo intero del telefono leggibile, nessun errore JS né CSP"),
    ("prova_scheda_intera.py", [], "telefono (06/10): una scheda a schermo intero (cruscotto dal menu, lavoro con il codice, documento con una tabella larga) a 3 dimensioni: testo ≥ 16 px, niente di lato, aggiornamento al suo posto senza perdere lo scorrimento, Chiudi, Esc, indietro, nessun errore JS"),
    # ~15 s: la pagina in Edge o Chromium senza finestra; senza browser si salta
    ("prova_schermi_satellite.py", [], "uno schermo per satellite: riusato ai ricollegamenti e dopo i riavvii, token rinnovato se perso, revoca a cascata, abbinamenti inattivi segnalati"),
    ("prova_schermi_pagina.py", [], "pagina degli schermi in un browser vero: si ricollega da sola dopo un riavvio"),
    # ~10 s: server degli schermi vero su 127.0.0.1, ufficio con l'estrazione finta
    ("prova_scritto_conversazione.py", [], "scrivere solo durante una conversazione a voce: regola pura, voce che apre e rinnova, breve e scritto che non rinnovano, altra persona e ospite che chiudono, server con evento «scrittura», 403 senza_conversazione e regola nel registro, modulo chiuso a metà"),
    ("prova_scritto.py", [], "scrivere invece di parlare: controlli dei codici, moduli dei tool con il server vero, valori al tool senza il modello, permessi, canale, registro"),
    # ~15 s: modulo e casella nella pagina vera (Edge o Chromium senza finestra); senza si salta
    ("prova_rispondi.py", [], "rispondi dove ti ho chiesto: scritto dal telefono con lo studio attivo, schermo senza audio, schermo_mostra, follow-up, annunci"),
    ("prova_scritto_pagina.py", [], "moduli nel browser vero: errore della cifra di controllo mentre si scrive, invio, casella"),
    # ~5 s: Pillow, Brain con un backend finto, server degli schermi vero, PC finto
    ("prova_immagini.py", [], "foto (05/10): controllo e riduzione dei byte, album della conversazione, foto nei messaggi, guardia sulle azioni, /api/immagine, pc_guarda e permessi, cattura dal satellite"),
    # ~8 s: file generati in memoria (anche ostili), Brain finto, server degli schermi vero
    ("prova_allegati.py", [], "allegati (05/10): tipo dai byte, lettura per tipo, file ostili (bomba zip, XXE, macro, PDF rotto, eseguibili), audio, contenuto marcato e guardia, allegato_leggi/archivia, delega, /api/allegato"),
    # ~15 s: la pagina in Edge o Chromium senza finestra; senza browser si salta
    ("prova_immagini_pagina.py", [], "foto nella pagina vera: pulsante, file scelto, incolla, trascina, SVG rifiutato, scheda con la miniatura"),
    # ~40 s: Calliope vera con un satellite finto; senza voci di Piper o modelli si salta
    ("prova_scritto_calliope.py", [], "testo scritto, modulo e foto dentro Calliope vera: nome tolto, niente STT, foto in attesa, registro e terminale senza codici né byte"),
    # ~6 s: server degli schermi e dei satelliti veri, client WebSocket finti
    ("prova_telefono.py", [], "telefono (web app): file e CSP, modelli col token, abbinamento e protocollo, prendi/lascia, CA di casa"),
    # ~60 s: la web app in Edge o Chromium senza finestra con il microfono finto; senza
    # browser, onnxruntime-web, modelli della wake word o voci di Piper si salta
    ("prova_telefono_pagina.py", [], "telefono nel browser vero: wake word e VAD come in Python, niente audio senza il nome, voce e barge-in"),
    # ~12 s: abbinamento del telefono che riprende dopo la pagina sospesa (iOS); con Edge o
    # Chromium anche nel browser vero, senza si fa solo la parte a secco
    ("prova_telefono_abbina.py", [], "telefono: abbinamento che riprende (ripresa segreta, token una volta sola, niente orfani), sessione che riprende al ritorno in primo piano"),
    # ~70 s: diagnostica e microfono del telefono; con Edge o Chromium e una voce di Piper anche
    # nel browser vero (microfono finto a 44,1 e 48 kHz, contesto forzato), Whisper se in cache
    ("prova_telefono_audio.py", [], "telefono: audio del microfono giusto (durata, contenuto, contesto rifatto), «Prova il microfono» e il suo endpoint"),
    # ~10 s: schermo acceso e vista da guida, in Edge o Chromium (senza si salta) con una
    # Screen Wake Lock API finta che vuole il gesto come WebKit
    ("prova_telefono_schermo.py", [], "telefono: schermo tenuto acceso col microfono (richiesta nel tocco, ripresa, avviso se negato o assente, versioni di iOS), vista da guida in uno schermo a 3 dimensioni"),
    ("prova_agenti.py", [], "agenti: tunnel con ssh finto, sandbox, Ollama finto, arbitro, tool, permessi"),
    ("prova_archivio.py", [], "archivio dei documenti di casa: grafo, deduplicazione, permessi, tool, agente, riprocessamento"),
    # ~12 s: docker finto, container usa-e-getta simulati
    ("prova_estensioni.py", [], "estensioni e guardrail: manifesto, porta stretta, azioni pericolose sospese e confermate, sfida, versioni, impronta"),
    # ~5 s: hub degli schermi vero, server su 127.0.0.1, docker finto con il Node della macchina
    ("prova_giochi.py", [], "giochi e schede interattive (05/10): manifesto con la scheda, documento e CSP del riquadro, approvazione dei giochi puri, partite su uno schermo e condivise, chat e frasi col guardiano, azioni della porta, banco d'attacco dei messaggi, tempo di gioco dei minori, richieste ai tutori, test JavaScript"),
    # ~60 s: la pagina degli schermi in Edge o Chromium senza finestra (senza si salta)
    ("prova_giochi_pagina.py", [], "giochi nella pagina vera: il riquadro ostile non legge la pagina né il localStorage, niente rete né WebRTC, messaggi falsi rifiutati, cane da guardia (ciclo infinito, navigazione, inondazione), partita di tris tra due pagine"),
    ("prova_contesto_agenti.py", [], "contesto degli agenti (05/10): finestra dal setup, tetti della passata e del ragionamento, risultati lunghi in .calliope, diario del lavoro alle soglie, domanda a metà lavoro"),
    ("prova_estensioni_piano.py", [], "contratto delle capacità, piano di fattibilità, chiedi_permesso, guardia contro il ragionamento a vuoto (agente finto)"),
    ("prova_estensioni_attacchi.py", [], "banco d'attacco delle estensioni: rete interna, indirizzi travestiti, rebinding, slowloris, dati esca, flussi, contaminazione, scarica_esempio"),
    ("prova_sandbox.py", [], "sandbox in un container con un docker finto: scelta del motore, docker run, kill, capacità"),
    ("prova_agenti_domande.py", [], "agenti: domande a metà lavoro, file della persona all'agente (anche via satellite)"),
    ("prova_analisi_richiesta.py", [], "agenti: analisi della richiesta prima della proposta (chiara, raffinabile, vaga, c'è già, impossibile qui), ripieghi, fonte web, modulo, motivo del tetto in parole"),
    # ~14 s: Ollama finto (anche l'API OpenAI) e Schermi senza server
    ("prova_avanzamento.py", [], "agenti: avanzamento dei lavori sugli schermi in diretta: ritmo, chiave unica, spostamento, visibilità, pausa"),
    ("prova_esecuzione.py", [], "agenti: il programma finito eseguito in diretta sullo schermo (Python e C# con un docker finto), «eseguilo con…», «fermalo», tetti"),
    # ~70 s: Calliope vera in un sottoprocesso, satellite con microfono e casse finti in tempo
    # reale; senza voci di Piper o modelli della wake word fa solo la parte breve
    ("prova_satellite.py", [], "satelliti: abbinamento, token, TLS, wake word, streaming, barge-in, riconnessione, latenza"),
    # ~45 s: Calliope vera, due satelliti finti, CAM++ sulle voci di Piper; senza si salta
    ("prova_corsie_satelliti.py", [], "due satelliti insieme con Calliope vera: la conversazione segue la persona, ospiti e altre persone no, risposte in parallelo e coda oltre il limite, doppione"),
    # ~12 s: server e satellite veri su 127.0.0.1, PC finto sul satellite
    ("prova_esecutore.py", [], "esecutore remoto del PC: pc_* via satellite, maniglie, permessi, tempi massimi, consegna dei documenti"),
    # ~12 s: inoltro TCP del satellite per il telefono di casa; con openssl la CA di casa,
    # con Edge o Chromium anche la pagina /telefono attraverso l'inoltro
    ("prova_inoltro.py", [], "inoltro del satellite per il telefono: reti ammesse, limiti, TLS da capo a capo, Host e Origin, impronta nuova al ponte"),
    ("prova_web.py", [], "ricerca su internet con SearXNG e siti finti: privacy, SSRF, testo non fidato, azioni bloccate, agente"),
    ("prova_lavori_criteri.py", [], "criteri del banco dei documenti: titoli, dati in lettere, numeri ricavati"),
    ("prova_agenti_openai.py", [], "agenti con il motore «openai» (vLLM): traduzione, client, lavori, --prova"),
    ("prova_arbitro_vllm.py", [], "arbitro con l'agente su vLLM sulla GPU della voce: stessa_gpu, uno stream per thread, pausa, archivio e ufficio cedevoli"),
    ("prova_arbitro_pausa.py", [], "arbitro con la pausa di vLLM (modalità sviluppo): congela e riprende, ripieghi, scrittore dell'ufficio, ripresa garantita"),
    ("prova_linux.py", [], "DGX Linux simulata: VAD senza torch, capacità, Whisper su server, voce su vLLM"),
    ("prova_linux_import.py", [], "DGX Linux simulata, solo gli import di tutti i moduli (legata a brain, ciclo, main, config)"),
    ("prova_gestore.py", [], "gestore di Linux: installa, aggiorna, verifica, ritorno automatico e a mano"),
    # ~10 s: Ollama finto, riavvio simulato (servizio dei lavori chiuso e ricreato)
    ("prova_lavori_riavvio.py", [], "agenti: lavori che sopravvivono a un riavvio (stato su disco, interrotti annunciati con «Lo rifaccio?», «sì»/«no», sandbox riusata, scadenze, domande in attesa)"),
    ("prova_robustezza.py", [], "robustezza: i guasti dell'analisi del 03/10 non bloccano più Calliope"),
    # ~20 s (Windows PowerShell e curl.exe veri, uv finto); --vera: uv e Python veri (~1 min)
    ("prova_installa_satellite.py", [], "PC nuovo come satellite con un comando: pacchetto, chiave, installa.ps1, aggiornamento e ritorno indietro"),
    ("prova_zim.py", [],"lettore ZIM in puro Python: formato, redirect, xz/zstd, file rovinati"),
    ("prova_biblioteca_indice.py", [], "indice SQLite FTS5: ricerca, validità, annullo, processi"),
    # ~5 s; se il file ZIM non c'è (non è in git) salta ed esce con 0
    ("prova_biblioteca.py", [], "biblioteca offline: recall@3 e latenza della ricerca"),
]
CON_OLLAMA = [
    ("prova_calcola.py", [], "conti a voce con il modello"),
    ("prova_agenda.py", [], "timer e promemoria con il modello"),
    ("prova_memoria.py", [], "memoria in più sessioni con il modello"),
    ("prova_casa.py", ["1"], "liste, appuntamenti e memoria della casa con il modello"),
    ("prova_pc_ollama.py", ["1"], "PC a voce con il modello (PC finto)"),
    ("prova_documenti_ollama.py", ["1"], "documenti a voce con il modello (cartella temporanea)"),
    ("prova_ufficio_ollama.py", ["1"], "fatture, preventivi, DDT e rubrica a voce con il modello"),
    ("prova_casa_ha_ollama.py", ["1"], "casa a voce con il modello (HA finto e PC finto)"),
    ("prova_stato_ollama.py", ["1"], "stato e installazioni a voce con il modello (server finto)"),
    ("prova_personalita_ollama.py", ["1"], "tono di voce chiesto a voce (cambia_voce con tono, per_tutti) e tool dopo il cambio"),
    ("prova_modalita_ollama.py", ["1"], "modalità Star Trek chiesta a voce (cambia_voce con modalita), «non sento i suoni», tool dopo il cambio, i toni restano toni"),
    ("prova_minori_ollama.py", ["--giri", "1"], "minori (05/10): richieste esplicite, aggiramenti, pericolo, compiti con 5 tentativi, tool, contrari per gli adulti, con il guardiano"),
    ("prova_schermi_ollama.py", ["1"], "schermi a voce con il modello e il server vero; latenza"),
    ("prova_agenti_ollama.py", ["1"], "delega, stato e annullo a voce con il modello (agente finto)"),
    ("prova_archivio_ollama.py", ["1"], "documenti di casa a voce con il modello (archivio finto)"),
    ("prova_web_ollama.py", ["1"], "ricerca su internet a voce (SearXNG finto): biblioteca o web, iniezione, privacy"),
    ("prova_brain_ollama.py", ["1"], "tool di base con il modello"),
    ("prova_rinomina_ollama.py", ["1"], "rinominare chi parla: mai al primo turno, solo dopo il «sì»"),
    ("prova_allegati_ollama.py", ["1"], "allegati con gemma4: bolletta, Excel, PDF lungo, Word, archivia, spesa, vocale; banco di sicurezza (istruzioni nei file e negli audio, esci, sì procedi, sfida): zero azioni"),
    ("prova_risultati_ollama.py", ["1"], "il risultato di un lavoro finito con gemma4 (07/10, caso della DGX): «E il risultato?», «leggili e dammi un bel riassunto» subito dopo l'annuncio, senza lavori_esegui né lavori_rispondi"),
    ("prova_conferma_unica_ollama.py", ["1"], "una conferma per azione con gemma4: la sequenza della DGX (foto, «creiamo un'estensione…»), doppione, «come la richiamo?»"),
    ("prova_politica_ollama.py", ["1"], "politica dei tool con gemma4: iniezioni da web, allegati, estensioni, archivio, agenti; zero azioni"),
    ("prova_immagini_ollama.py", ["1"], "foto con gemma4: scontrino e turno dopo, spesa dallo scontrino, istruzione nella foto senza azioni, archivia, schermo e webcam"),
    ("prova_scritto_ollama.py", ["1"], "la voce che offre lo schermo per i dati da scrivere (ufficio vero, pagina finta)"),
    ("prova_date_ricordi_ollama.py", ["1"], "conversazione vera della DGX del 05/10 18:10: età e date con data_calcola, ricordi solo quando pertinenti, «fermati con l'ordine» senza stati inventati"),
    ("prova_regressione.py", ["1"], "banco di regressione dalle frasi vere (ora, chi sono, casa, annulla…)"),
    ("prova_prompt_conversazione.py", ["1"], "conversazione a più turni (il «che voci hai?» è un limite noto)"),
    ("prova_biblioteca.py", ["--ollama"], "biblioteca end-to-end, con e senza (~5 minuti)"),
]


def keep_alive_della_voce():
    """Il keep_alive del modello della voce di questa installazione (calliope.yaml, il file
    locale, il profilo), o None. Le prove con Ollama lo mandano uguale (04/10): con il 30m
    dei predefiniti di Config() una prova toglieva il «sempre caricato» (-1) del modello
    condiviso con la voce, che poi pagava secondi a ricaricarlo dopo una pausa."""
    import contextlib
    import io
    try:
        from calliope.config import load_config
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            cfg = load_config(str(RADICE / "calliope.yaml"))
        return cfg.llm_keep_alive
    except Exception:  # noqa: BLE001 — senza configurazione leggibile: quello delle prove
        return None


# ─────────────────────────── livelli (06/10, P5 dell'analisi complessiva) ───────────────────────────
# Livello 1 (ogni prova non elencata qui sotto): veloce, sempre, in parallelo.
# Livello 2: solo se il commit tocca i file legati (LEGAMI), in parallelo.
# Livello 3: lunghe, browser, Calliope vera, tempo reale: solo con --completo, in serie;
# OBBLIGATORIO prima dell'unione su main.
# Le durate tra parentesi sono del 06/10 sul portatile, nel gruppo parallelo.
LIVELLO_2 = {
    "prova_casa_ha.py",              # 13 s
    "prova_capacita.py",             # 11 s
    "prova_installa.py",             # 6 s
    "prova_schermi.py",              # 13 s
    "prova_cruscotto.py",            # 3 s
    "prova_scritto.py",              # 5 s
    "prova_agenti.py",               # 55–60 s
    "prova_sandbox.py",              # 10 s
    "prova_agenti_domande.py",       # 9 s
    "prova_analisi_richiesta.py",    # 8 s
    "prova_avanzamento.py",          # 16 s
    "prova_esecuzione.py",           # 17 s
    "prova_agenti_openai.py",        # 9 s
    "prova_arbitro_vllm.py",         # 19 s
    "prova_arbitro_pausa.py",        # 21 s
    "prova_estensioni.py",           # 16 s
    "prova_estensioni_attacchi.py",  # 30 s
    "prova_giochi.py",               # 7 s
    "prova_esecutore.py",            # 12 s
    "prova_inoltro.py",              # 18 s, con il browser (seriale)
    "prova_telefono_abbina.py",      # 12 s, con il browser (seriale)
    "prova_linux.py",                # 13 s
    "prova_linux_import.py",         # 5 s: solo gli import della DGX simulata (Q7, 06/10)
    "prova_gestore.py",              # 10 s
    "prova_lavori_riavvio.py",       # 10 s
    "prova_robustezza.py",           # 15 s (88 s prima del 06/10: aspettava il guardiano)
    "prova_biblioteca.py",           # 6 s, con i file della biblioteca
    "prova_markdown.py",             # 8 s (07/10)
    "prova_pause.py",                # 9 s (07/10)
}
LIVELLO_3 = {
    "prova_schermi_pagina.py", "prova_scritto_pagina.py", "prova_immagini_pagina.py",
    "prova_giochi_pagina.py", "prova_scritto_calliope.py", "prova_telefono_pagina.py",
    "prova_telefono_audio.py", "prova_telefono_schermo.py", "prova_satellite.py",
    "prova_corsie_satelliti.py", "prova_installa_satellite.py", "prova_cruscotto_pagina.py",
    "prova_scheda_intera.py", "prova_markdown_pagina.py",
}
# Mai nel gruppo parallelo, anche quando una prova li sceglie nel livello 2: un browser, un
# tempo reale o tanti processi, che sotto carico falliscono a caso. Tutto il livello 3 è
# seriale.
SERIALI = LIVELLO_3 | {"prova_inoltro.py", "prova_telefono_abbina.py"}
# Prefisso del percorso cambiato → prove del livello 2 (o 3) da lanciare nel hook. I file
# trasversali (brain.py, config.py, politica.py, tools/registry.py, tools/spec.py,
# tools/builtin.py…) scelgono solo prova_linux_import (gli import di tutto il pacchetto su
# Linux, ~5 s): il resto lo coprono il livello 1 e il livello 3 prima dell'unione. I tool
# d'area (tools/casa.py, tools/agenti.py…) scelgono le prove della loro area (Q7 della seconda
# analisi del 06/10: prima tutto tools/ era trasversale). Un file di prove/ sceglie sé stesso
# e le prove che lo importano (scelte da sole: vedi `_importatori`).
LEGAMI = [
    ("calliope/brain.py", ["prova_linux_import.py"]),
    ("calliope/ciclo.py", ["prova_linux_import.py"]),
    ("calliope/main.py", ["prova_linux_import.py"]),
    ("calliope/config.py", ["prova_linux_import.py"]),
    ("calliope/tools/casa.py", ["prova_casa_ha.py"]),
    ("calliope/tools/agenti.py", ["prova_agenti.py", "prova_agenti_domande.py",
                                 "prova_analisi_richiesta.py",
                                 "prova_esecuzione.py", "prova_avanzamento.py"]),
    ("calliope/tools/schermi.py", ["prova_schermi.py", "prova_scritto.py",
                                  "prova_risultati.py"]),
    ("calliope/tools/estensioni.py", ["prova_estensioni.py", "prova_estensioni_attacchi.py",
                                     "prova_analisi_richiesta.py",
                                     "prova_giochi.py"]),
    ("calliope/tools/pc.py", ["prova_esecutore.py"]),
    ("calliope/tools/stato.py", ["prova_capacita.py", "prova_installa.py"]),
    ("calliope/tools/ufficio.py", ["prova_scritto.py"]),
    ("calliope/tools/web.py", ["prova_web.py", "prova_estensioni_attacchi.py"]),
    ("calliope/tools/archivio.py", ["prova_archivio.py"]),
    ("calliope/tools/immagini.py", ["prova_immagini.py"]),
    ("calliope/tools/allegati.py", ["prova_allegati.py"]),
    ("calliope/tools/minori.py", ["prova_minori.py", "prova_giochi.py"]),
    ("calliope/speaker_id.py", ["prova_voci_famiglia.py", "prova_conferme.py"]),
    ("calliope/conferme.py", ["prova_voci_famiglia.py", "prova_conferme.py"]),
    ("calliope/minori.py", ["prova_voci_famiglia.py", "prova_minori.py"]),
    ("calliope/tools/documenti.py", ["prova_documenti.py", "prova_lavori_criteri.py"]),
    ("calliope/tools/conversazioni.py", ["prova_conversazioni.py"]),
    ("calliope/casa/", ["prova_casa_ha.py"]),
    ("calliope/capacita.py", ["prova_capacita.py"]),
    ("calliope/stato.py", ["prova_capacita.py"]),
    ("calliope/macchina.py", ["prova_capacita.py"]),
    ("calliope/installa/", ["prova_installa.py", "prova_capacita.py"]),
    ("calliope/latenza.py", ["prova_cruscotto.py"]),
    ("calliope/schermi/", ["prova_schermi.py", "prova_cruscotto.py", "prova_scritto.py", "prova_giochi.py",
                           "prova_telefono_abbina.py", "prova_inoltro.py",
                           "prova_immagini.py", "prova_allegati.py"]),
    ("calliope/ufficio/", ["prova_scritto.py"]),
    ("calliope/immagini.py", ["prova_immagini.py"]),
    ("calliope/allegati.py", ["prova_allegati.py"]),
    ("calliope/agenti/", ["prova_agenti.py", "prova_sandbox.py", "prova_agenti_domande.py",
                          "prova_avanzamento.py", "prova_esecuzione.py",
                          "prova_agenti_openai.py", "prova_arbitro_vllm.py",
                          "prova_arbitro_pausa.py", "prova_contesto_agenti.py",
                          "prova_estensioni_piano.py", "prova_analisi_richiesta.py"]),
    ("calliope/estensioni/",
 ["prova_estensioni.py", "prova_estensioni_piano.py",
                              "prova_estensioni_attacchi.py", "prova_giochi.py"]),
    ("calliope/guardrail.py", ["prova_estensioni.py", "prova_estensioni_attacchi.py"]),
    ("calliope/web/", ["prova_web.py", "prova_estensioni_attacchi.py"]),
    ("calliope/archivio/", ["prova_archivio.py"]),
    ("calliope/documenti/", ["prova_lavori_criteri.py", "prova_markdown.py"]),
    # Il Markdown dell'agente, il lettore e «Scarica» (07/10)
    ("calliope/schermi/", ["prova_markdown.py"]),
    ("calliope/agenti/", ["prova_markdown.py"]),
    ("calliope/tools/agenti.py", ["prova_markdown.py"]),
    ("calliope/satellite/", ["prova_esecutore.py", "prova_inoltro.py",
                             "prova_telefono_abbina.py"]),
    ("calliope/pc/", ["prova_esecutore.py"]),
    ("calliope/vad.py", ["prova_linux.py"]),
    ("calliope/stt.py", ["prova_linux.py", "prova_robustezza.py"]),
    ("setup/linux/", ["prova_linux.py", "prova_gestore.py"]),
    ("prove/e2e/", ["prova_e2e_copioni.py"]),
    # I lavori che sopravvivono a un riavvio (06/10)
    ("calliope/agenti/", ["prova_lavori_riavvio.py"]),
    ("calliope/tools/agenti.py", ["prova_lavori_riavvio.py"]),
    ("calliope/main.py", ["prova_robustezza.py"]),
    ("calliope/ciclo.py", ["prova_robustezza.py"]),
    ("calliope/tts.py", ["prova_robustezza.py"]),
    ("calliope/audio.py", ["prova_robustezza.py"]),
    ("calliope/persistenza.py", ["prova_robustezza.py"]),
    ("calliope/turnlog.py", ["prova_robustezza.py"]),
    ("calliope/zim.py", ["prova_zim.py", "prova_biblioteca.py"]),
    ("calliope/biblioteca", ["prova_biblioteca_indice.py", "prova_biblioteca.py"]),
    # Pause e fine del turno (07/10, solo misura): dove sta il VAD e il registro
    ("calliope/pause.py", ["prova_pause.py"]),
    ("calliope/audio.py", ["prova_pause.py"]),
    ("calliope/ciclo.py", ["prova_pause.py"]),
    ("calliope/stato.py", ["prova_pause.py"]),
    ("calliope/satellite/", ["prova_pause.py"]),
    ("calliope/schermi/telefono.py", ["prova_pause.py"]),
    ("calliope/schermi/pagina/telefono/", ["prova_pause.py"]),
    ("pyproject.toml", ["prova_linux.py", "prova_gestore.py"]),
    ("uv.lock", ["prova_linux.py"]),
]
# Prove che il runner non lancia, con il perché (06/10, Q7): prova_runner controlla che ogni
# prove/prova_*.py sia in A_SECCO, in CON_OLLAMA o qui. Una prova nuova dimenticata fallisce.
MANUALI = {
    "prova_aec.py": "fattibilità della cancellazione dell'eco: sottocomandi con audio vero",
    "prova_confronto.py": "misura storica con Ollama (reasoning_effort e tool)",
    "prova_ctx.py": "misura storica con Ollama (token del prompt e num_ctx)",
    "prova_debug.py": "ispezione a mano di schemi, prompt e risposta grezza di Ollama",
    "prova_estensioni_agente.py": "sulla DGX, con l'agente vero e il container vero",
    "prova_estensioni_ollama.py": "con il modello vero della voce, lunga: a mano dopo le "
                                  "modifiche alle estensioni",
    "prova_latency.py": "misura storica con Ollama (thinking acceso contro spento)",
    "prova_lavori.py": "banco degli agenti: decine di minuti con il modello vero (--dgx)",
    "prova_llm.py": "misura storica del ciclo dei tool contro Ollama",
    "prova_native.py": "misura storica dell'API nativa di Ollama",
    "prova_native2.py": "misura storica dell'API nativa di Ollama (think)",
    "prova_native3.py": "misura storica dell'API nativa di Ollama (ciclo completo)",
    "prova_numctx.py": "misura storica di num_ctx sull'endpoint OpenAI (con ollama ps)",
    "prova_ollama_tool.py": "ispezione a mano dei tool_calls di Ollama",
    "prova_prompt.py": "confronto storico di varianti di prompt con Ollama",
    "prova_prompt2.py": "confronto storico di varianti di prompt con Ollama",
    "prova_prompt3.py": "confronto storico di varianti di prompt con Ollama",
    "prova_prompt4.py": "confronto storico di varianti di prompt con Ollama",
    "prova_speaker.py": "confronto dei modelli di chi parla: sottocomandi con dati scaricati",
    "prova_tool_scala.py": "banco «molti tool» con un LLM piccolo (minuti, con Ollama)",
    "prova_wakeword.py": "wake word dal microfono o sulle registrazioni (fuori da git)",
    "prova_whisper.py": "taratura di Whisper sulle registrazioni (fuori da git)",
}
TIMEOUT_S = 300           # per prova; con --ollama TIMEOUT_OLLAMA_S
TIMEOUT_OLLAMA_S = 3600
SALTATA = 77              # codice d'uscita di una prova saltata per intero
PARZIALE = "SALTATA IN PARTE:"   # riga stampata da una prova che salta una sua parte
LENTA_S = 10.0            # una prova del livello 1 oltre questo tempo va spostata


def livello(script: str) -> int:
    return 3 if script in LIVELLO_3 else 2 if script in LIVELLO_2 else 1


def _git(*args: str, radice: Path = RADICE) -> list[str]:
    try:
        r = subprocess.run(["git", "-C", str(radice), *args], capture_output=True,
                           timeout=30, env=_senza_git(os.environ))
    except (OSError, subprocess.SubprocessError):
        return []
    if r.returncode != 0:
        return []
    return [x for x in r.stdout.decode("utf-8", "replace").split("\0") if x]


def _senza_git(env) -> dict:
    """L'ambiente senza GIT_*: dentro l'hook git passa GIT_DIR, GIT_INDEX_FILE… (in un worktree
    anche per il repository principale), e le prove che creano repository temporanei
    (prova_gestore) finirebbero a scrivere nell'indice del commit in corso (02/10)."""
    return {k: v for k, v in env.items() if not k.startswith("GIT_")}


def file_cambiati(modo: str) -> list[str] | None:
    """I percorsi cambiati, relativi alla radice. `indice`: quello che si sta per committare;
    `ramo`: dal punto in cui il ramo si è staccato da main, più l'albero di lavoro; altrimenti
    l'albero di lavoro e l'indice rispetto a HEAD, più i file nuovi. None fuori da git."""
    if os.environ.get("PROVE_FILE_CAMBIATI") is not None:     # la copia di --staged
        return [x for x in os.environ["PROVE_FILE_CAMBIATI"].split("\n") if x]
    if not (RADICE / ".git").exists():
        return None
    if modo == "indice":
        return _git("diff", "--cached", "--name-only", "-z")
    nomi = _git("diff", "HEAD", "--name-only", "-z")
    nomi += _git("ls-files", "--others", "--exclude-standard", "-z")
    if modo == "ramo":
        base = _git("merge-base", "HEAD", "main")
        if base:
            nomi += _git("diff", base[0].strip(), "HEAD", "--name-only", "-z")
    return sorted(set(nomi))


def _importatori(modulo: str) -> list[str]:
    """Le prove che importano un modulo di prove/ (import X, from X import, import X as)."""
    import re
    pat = re.compile(rf"^\s*(from\s+(prove\.)?{re.escape(modulo)}\s+import|import\s+(prove\.)?"
                     rf"{re.escape(modulo)}\b)", re.M)
    out = []
    for p in sorted((RADICE / "prove").glob("prova_*.py")):
        try:
            if pat.search(p.read_text(encoding="utf-8", errors="replace")):
                out.append(p.name)
        except OSError:
            pass
    return out


def scelte_dai_file(cambiati: list[str]) -> dict[str, str]:
    """prova → motivo (il primo file che la sceglie)."""
    scelte: dict[str, str] = {}
    for f in cambiati:
        f = f.replace("\\", "/")
        for pref, prove in LEGAMI:
            if f.startswith(pref):
                for p in prove:
                    scelte.setdefault(p, f)
        if f.startswith("prove/") and f.endswith(".py") and "/" not in f[6:]:
            # sé stessa e chi la importa, anche attraverso altre prove (cdp.py →
            # prova_schermi_pagina → prova_scritto_pagina)
            da_fare, visti = [f[6:]], set()
            while da_fare:
                nome = da_fare.pop()
                if nome in visti:
                    continue
                visti.add(nome)
                if nome.startswith("prova_"):
                    scelte.setdefault(nome, f)
                da_fare += _importatori(nome[:-3])
    return scelte


# ─────────────────────────── esecuzione ───────────────────────────
def lancia(script: str, args: list[str], timeout: float = TIMEOUT_S) -> dict:
    # Le prove non leggono calliope.locale.yaml: con l'indirizzo di casa impostato,
    # una prova (anche prima di un commit) contatterebbe Home Assistant. Né dgx.yaml: una
    # prova non deve mai aprire un tunnel verso la DGX vera (02/10)
    env = dict(_senza_git(os.environ), PYTHONUTF8="1",
               CALLIOPE_CONFIG_LOCALE=str(RADICE / "prove" / "nessun-file-locale.yaml"),
               CALLIOPE_AGENTI_CONFIG=str(RADICE / "prove" / "nessun-file-dgx.yaml"),
               # Niente taratura della voce all'avvio (07/10): con Calliope vera proverebbe i
               # thread di Piper a ogni prova, CPU tolta alle altre in parallelo
               CALLIOPE_TTS_TARATURA="false")
    env.pop("CALLIOPE_AGENTI_URL", None)
    env.pop("CALLIOPE_SSH", None)
    env.pop("PROVE_FILE_CAMBIATI", None)
    cmd = [sys.executable, "-u", str(RADICE / "prove" / script), *args]
    t0 = time.perf_counter()
    rc, out, vivi, scaduta = _esegui(cmd, env, timeout)
    dt = time.perf_counter() - t0
    if scaduta:
        out += f"\nERR tempo scaduto: più di {timeout:.0f} s (prova chiusa dal runner)\n"
        rc = 1
    elif vivi:
        # Un figlio rimasto vivo (Calliope, un browser, un server finto) tiene porte, file e
        # CPU durante le prove dopo e le fa fallire a caso: è un errore di questa prova (03/10)
        out += ("\nERR processi lasciati vivi dalla prova (chiusi dal runner): "
                + "; ".join(vivi) + "\n")
        rc = rc or 1
    esito = "saltata" if rc == SALTATA else "ok" if rc == 0 else "fallita"
    parziali = [r[len(PARZIALE):].strip() for r in out.splitlines() if r.startswith(PARZIALE)]
    return {"script": script, "args": args, "esito": esito, "dt": dt, "out": out,
            "parziali": parziali}


def _esegui(cmd: list[str], env: dict, timeout: float) -> tuple[int, str, list[str], bool]:
    """Lancia una prova. Su Windows dentro un job object (03/10): a prova finita si vede se
    ha lasciato processi vivi (su Windows i figli non muoiono con il padre) e il runner li
    chiude; allo scadere del tempo massimo si chiude tutto il job. Altrove un gruppo di
    processi suo. L'output si legge in un thread: un figlio rimasto vivo con la pipe
    ereditata non tiene fermo il runner (con `subprocess.run` aspettava la sua fine)."""
    job = None
    if sys.platform == "win32":
        try:
            from calliope.agenti import winjob
            job = winjob.JobObject()
        except Exception:  # noqa: BLE001
            job = None
    kw = dict(cwd=RADICE, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    if job is None and sys.platform != "win32":
        kw["start_new_session"] = True
    proc = winjob.avvia_nel_job(cmd, job, **kw) if job is not None else subprocess.Popen(cmd, **kw)
    pezzi: list[bytes] = []

    def leggi():
        for blocco in iter(lambda: proc.stdout.read1(65536), b""):
            pezzi.append(blocco)
    lettore = threading.Thread(target=leggi, daemon=True)
    lettore.start()
    scaduta = False
    try:
        rc = proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        scaduta = True
        if job is not None:
            job.termina()
        elif sys.platform != "win32":
            import signal
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except OSError:
                proc.kill()
        else:
            proc.kill()
        rc = proc.wait(timeout=30)
    vivi: list[str] = []
    if job is not None:
        if not scaduta:
            fine = time.monotonic() + 2.0   # un figlio che si sta chiudendo da solo proprio ora
            while (vivi := _processi_nel_job(job)) and time.monotonic() < fine:
                time.sleep(0.1)
        job.termina()
        job.close()
    lettore.join(10)
    out = b"".join(pezzi).decode("utf-8", "replace").replace("\r\n", "\n")
    return rc, out, vivi, scaduta


def _processi_nel_job(job) -> list[str]:
    """I processi ancora vivi nel job (JobObjectBasicProcessIdList), con nome e comando."""
    import ctypes
    from ctypes import wintypes

    class _Elenco(ctypes.Structure):
        _fields_ = [("assegnati", wintypes.DWORD), ("nell_elenco", wintypes.DWORD),
                    ("pid", ctypes.c_size_t * 512)]
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    k32.QueryInformationJobObject.restype = wintypes.BOOL
    k32.QueryInformationJobObject.argtypes = (wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p,
                                              wintypes.DWORD, ctypes.c_void_p)
    el = _Elenco()
    if not k32.QueryInformationJobObject(job.handle, 3, ctypes.byref(el), ctypes.sizeof(el),
                                         None):
        return []
    nomi = []
    for pid in el.pid[:el.nell_elenco]:
        try:
            import psutil
            p = psutil.Process(pid)
            nomi.append(f"{p.name()} ({pid}): " + " ".join(p.cmdline())[:200])
        except Exception:  # noqa: BLE001
            nomi.append(f"pid {pid}")
    return nomi


def _riassunto(out: str) -> list[str]:
    """Le righe d'errore della prova; di ogni traceback anche l'ultima riga (l'eccezione):
    prima si vedeva solo «Traceback (most recent call last):» (03/10)."""
    scelte, in_tb = [], False
    for r in (r for r in out.splitlines() if r.strip()):
        if r.startswith("Traceback"):
            in_tb = True
            scelte.append(r)
        elif in_tb and not r.startswith((" ", "\t")):
            in_tb = False
            scelte.append("  " + r)
        elif not in_tb and r.startswith(("ERR", "NO ")):
            scelte.append(r)
    return scelte or [r for r in out.splitlines() if r.strip()]


_STAMPA = threading.Lock()
CARTELLA_LOG = Path(tempfile.gettempdir()) / "calliope-prove"
FILE_DURATE = CARTELLA_LOG / "durate.json"


def _durate() -> dict:
    import json
    try:
        return json.loads(FILE_DURATE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _salva_durate(esiti: list[dict]):
    import json
    d = _durate()
    for e in esiti:
        if e["esito"] == "ok":
            d[e["script"]] = round(e["dt"], 1)
    try:
        CARTELLA_LOG.mkdir(parents=True, exist_ok=True)
        FILE_DURATE.write_text(json.dumps(d, indent=1, sort_keys=True), encoding="utf-8")
    except OSError:
        pass


def stampa(e: dict, cosa: str, liv: int):
    nome = " ".join([e["script"], *e["args"]])
    segno = {"ok": "ok ", "saltata": "-- ", "fallita": "ERR"}[e["esito"]]
    righe = [f"{segno} {e['dt']:5.1f}s  L{liv} {nome:38} {cosa}"]
    if e["esito"] == "saltata":
        motivo = next((r for r in reversed(e["out"].splitlines()) if r.strip()), "")
        righe.append(f"      │ SALTATA: {motivo[:150]}")
    for p in e["parziali"]:
        righe.append(f"      │ {PARZIALE} {p[:150]}")
    if e["esito"] == "fallita":
        for r in _riassunto(e["out"])[-12:]:
            righe.append(f"      │ {r}")
        # L'output intero resta in un file: una prova instabile fallisce di rado, e le
        # righe qui sopra di solito non bastano a capire perché (03/10)
        log = CARTELLA_LOG / f"{e['script']}.{os.getpid()}.log"
        try:
            log.parent.mkdir(parents=True, exist_ok=True)
            log.write_text(e["out"], encoding="utf-8")
            righe.append(f"      │ (output intero in {log})")
        except OSError:
            pass
    with _STAMPA:
        print("\n".join(righe), flush=True)


def esegui_tutte(prove: list[tuple], paralleli: int, timeout: float) -> list[dict]:
    """Le prove non seriali in parallelo (le più lunghe prima, dalle durate dell'ultima
    volta), poi le seriali una alla volta, da sole sulla macchina."""
    from concurrent.futures import ThreadPoolExecutor
    durate = _durate()
    gruppo = [p for p in prove if p[0] not in SERIALI]
    serie = [p for p in prove if p[0] in SERIALI]
    gruppo.sort(key=lambda p: -durate.get(p[0], 5.0))
    esiti = []

    def una(p):
        script, args, cosa = p
        e = lancia(script, args, timeout)
        stampa(e, cosa, livello(script))
        return e
    if gruppo:
        if paralleli > 1 and len(gruppo) > 1:
            with ThreadPoolExecutor(max_workers=paralleli) as ex:
                esiti += list(ex.map(una, gruppo))
        else:
            esiti += [una(p) for p in gruppo]
    if serie and gruppo:
        print(f"── in serie: {len(serie)} prove (browser, Calliope vera, tempo reale)", flush=True)
    esiti += [una(p) for p in serie]
    return esiti


# ─────────────────────────── --staged: la copia dell'indice ───────────────────────────
def con_indice(argv: list[str]) -> int:
    """Rilancia il runner su una copia dell'indice di git (git checkout-index in una cartella
    temporanea): si prova quello che si sta per committare, non l'albero di lavoro (un file
    cambiato e non aggiunto non conta). Non tocca indice, albero di lavoro né stash
    dell'utente. I file grossi fuori da git (voices/, models/, wakeword/modelli/,
    biblioteca/) entrano nella copia come hard link (`_risorse`); dove non si può (un altro
    disco) le prove che li vogliono si saltano."""
    import shutil
    if not (RADICE / ".git").exists():
        print("--staged: non è un repository git", flush=True)
        return 1
    copia = Path(tempfile.mkdtemp(prefix="calliope-indice-"))
    try:
        r = subprocess.run(["git", "-C", str(RADICE), "checkout-index", "-a",
                            f"--prefix={copia.as_posix()}/"], capture_output=True,
                           env=_senza_git(os.environ), timeout=300)
        if r.returncode != 0:
            print("--staged: copia dell'indice non riuscita: "
                  + r.stderr.decode("utf-8", "replace")[-300:], flush=True)
            return 1
        _risorse(copia)
        modo = "ramo" if "--ramo" in argv else "indice" if "--hook" in argv else "albero"
        cambiati = file_cambiati(modo) or []
        # PROVE_ORIGINE: da dove viene la copia (prova_dati_privati vi cerca privato/termini.txt)
        env = dict(os.environ, PROVE_FILE_CAMBIATI="\n".join(cambiati), PROVE_ORIGINE=str(RADICE))
        resto = [a for a in argv if a != "--staged"]
        print(f"Prove sulla copia dell'indice di git ({copia})", flush=True)
        return subprocess.run([sys.executable, "-m", "prove", *resto], cwd=copia,
                              env=env).returncode
    finally:
        shutil.rmtree(copia, ignore_errors=True)


RISORSE = ("voices/*.onnx", "voices/*.onnx.json", "models/speaker/*.onnx", "models/web/**/*",
           "wakeword/modelli/*.onnx", "biblioteca/*.zim", "biblioteca/*.sha256",
           "biblioteca/*.verificato", "biblioteca/indici/*.sqlite")


def _risorse(copia: Path):
    """I modelli e i file grossi fuori da git nella copia, come hard link: niente byte copiati,
    e cancellare la copia toglie solo i link."""
    for pat in RISORSE:
        for f in RADICE.glob(pat):
            d = copia / f.relative_to(RADICE)
            if not f.is_file() or d.exists():
                continue
            try:
                d.parent.mkdir(parents=True, exist_ok=True)
                os.link(f, d)
            except OSError:
                return              # un altro disco, o un file system senza hard link


AIUTO = """Uso: python -m prove [opzioni] [prova_x.py …]

    (niente)        livello 1 (veloci, in parallelo) + livello 2 (legate ai file cambiati
                    rispetto a HEAD, compresi quelli nuovi)
    --hook          come sopra con i file dell'indice (lo usa .githooks/pre-commit)
    --ramo          livello 2 con tutti i file cambiati dal punto in cui il ramo si è staccato da main
    --completo      TUTTE le prove a secco: livelli 1 e 2 in parallelo, poi il 3 in serie
                    (browser, Calliope vera, tempo reale). Obbligatorio prima dell'unione su main
    --staged        prova la copia dell'indice di git, non l'albero di lavoro
    --ollama        anche le prove con il modello vero (in serie, dopo)
    --seriale       una prova alla volta (-j 1); -j N: N prove insieme
    --timeout S     tempo massimo per prova (predefinito 300 s)
    prova_x.py …    solo queste (con il livello e il parallelo di sempre)
Codici: 0 tutto bene, 1 qualche prova fallita. Una prova che esce con 77 è SALTATA (contata a parte)."""


def main(argv: list[str]) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")    # «│» e accenti anche nella console cp1252
    except (AttributeError, ValueError):
        pass
    if "-h" in argv or "--help" in argv:
        print(AIUTO)
        return 0
    if "--staged" in argv and os.environ.get("PROVE_FILE_CAMBIATI") is None:
        return con_indice(argv)
    paralleli = min(6, os.cpu_count() or 2)
    if "--seriale" in argv:
        paralleli = 1
    if "-j" in argv:
        paralleli = max(1, int(argv[argv.index("-j") + 1]))
    timeout = float(argv[argv.index("--timeout") + 1]) if "--timeout" in argv else TIMEOUT_S
    t_tot = time.perf_counter()

    nomi = [a for a in argv if a.endswith(".py")]
    completo = "--completo" in argv
    if nomi:
        # `python -m prove prova_satellite.py prova_agenti.py`: solo quelle (03/10)
        scelte = [p for p in A_SECCO if p[0] in nomi]
        print(f"Solo {len(scelte)} prove scelte", flush=True)
    elif completo:
        scelte = list(A_SECCO)
        print(f"Completo: {len(scelte)} prove a secco (livelli 1, 2 e 3), {paralleli} alla "
              f"volta, poi le seriali una alla volta", flush=True)
    else:
        modo = "indice" if "--hook" in argv else "ramo" if "--ramo" in argv else "albero"
        cambiati = file_cambiati(modo)
        legate = scelte_dai_file(cambiati) if cambiati is not None else {}
        if cambiati is None:
            print("Fuori da git: livello 2 con tutte le sue prove", flush=True)
            legate = {p[0]: "fuori da git" for p in A_SECCO if livello(p[0]) == 2}
        legate = {k: v for k, v in legate.items() if livello(k) >= 2}
        scelte = [p for p in A_SECCO if livello(p[0]) == 1 or p[0] in legate]
        uno = sum(1 for p in scelte if livello(p[0]) == 1)
        print(f"Livello 1: {uno} prove veloci, {paralleli} alla volta", flush=True)
        if legate:
            print("Livello 2 (file cambiati): " + ", ".join(
                f"{p[:-3].removeprefix('prova_')} ← {legate[p]}"
                for p in sorted(legate, key=lambda x: legate[x])), flush=True)
        saltate3 = [p[0] for p in A_SECCO if livello(p[0]) == 3 and p[0] not in legate]
        if saltate3:
            print(f"Livello 3 non lanciato ({len(saltate3)} prove): prima dell'unione su main "
                  f"python -m prove --completo", flush=True)
    esiti = esegui_tutte(scelte, paralleli, timeout)
    _salva_durate(esiti)

    if "--ollama" in argv:
        if "CALLIOPE_LLM_KEEP_ALIVE" not in os.environ:
            ka = keep_alive_della_voce()
            if ka is not None:
                # Le prove lo ereditano (lancia copia os.environ): Config() lo legge da qui
                os.environ["CALLIOPE_LLM_KEEP_ALIVE"] = str(ka)
                print(f"keep_alive delle prove con Ollama: {ka} (quello della voce)", flush=True)
        oll = [p for p in CON_OLLAMA if not nomi or p[0] in nomi]
        for script, args, cosa in oll:
            e = lancia(script, args, max(timeout, TIMEOUT_OLLAMA_S))
            stampa(e, cosa, 0)
            esiti.append(e)

    fallite = [" ".join([e["script"], *e["args"]]) for e in esiti if e["esito"] == "fallita"]
    saltate = [e["script"] for e in esiti if e["esito"] == "saltata"]
    parziali = [e["script"] for e in esiti if e["parziali"]]
    lente = [f"{e['script']} {e['dt']:.0f} s" for e in esiti
             if livello(e["script"]) == 1 and e["esito"] == "ok"
             and e["dt"] > LENTA_S * (1 if paralleli == 1 else 2)
             and e["script"] in {p[0] for p in A_SECCO}]
    superate = sum(1 for e in esiti if e["esito"] == "ok")
    print(f"\n{superate}/{len(esiti)} prove superate, {len(saltate)} saltate, "
          f"{len(fallite)} fallite in {time.perf_counter() - t_tot:.1f}s", flush=True)
    if saltate:
        print("   saltate: " + ", ".join(saltate))
    if parziali:
        print("   saltate in parte: " + ", ".join(parziali))
    if lente:
        print("   lente per il livello 1 (spostale al 2 o al 3 in prove/__main__.py): "
              + ", ".join(lente))
    if fallite:
        print("   fallite: " + ", ".join(fallite))
    return 1 if fallite else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
