"""Frasi del banco della preselezione dei tool (15/10/2026, calliope/system1/preselezione.py;
ricerca docs/ricerche/2026-10-15-preselezione-tool.md).

Frasi vocali in italiano con i tool **veri** di Calliope che il modello potrebbe chiamare: una
frase è presa se l'insieme scelto contiene **almeno uno** dei tool accettati (per «Ricordami di
comprare il latte» vanno bene la lista e il promemoria). `()` = nessun tool serve: lì l'insieme
piccolo è un risparmio, mai un errore. Sono parafrasi scritte apposta, non gli esempi tra
virgolette delle descrizioni dei tool (che il preselettore usa come prototipi): misurare sugli
stessi esempi direbbe solo che li sa a memoria. Una parte viene dalle richieste del banco del
26/09 (docs/ricerche/banchi/ricerca_tool/richieste.py) con i nomi veri di oggi.

Ogni caso: (frase, tool accettati, frase di prima o None, tool usati nella conversazione).
Solo nomi e dati di fantasia. Li usano prove/prova_preselezione.py (a secco) e
prove/manuali/preselezione_dgx.py (la latenza col modello della DGX)."""

C = []


def f(frase, *tool, prima=None, recenti=()):
    C.append((frase, tuple(tool), prima, tuple(recenti)))


# ── tempo e calcoli ──
f("Che ore sono?", "ora_attuale")
f("Calliope, che ore sono?", "ora_attuale")
f("Che ore so", "ora_attuale")
f("Mi sai dire l'ora?", "ora_attuale")
f("Che giorno è oggi?", "data_oggi")
f("Oggi che data abbiamo?", "data_oggi")
f("Quanto fa diciassette per ventitré?", "calcola")
f("Il venti per cento di trecentoquaranta euro quant'è?", "calcola")
f("Radice quadrata di centoquarantaquattro", "calcola")
f("Quanti giorni mancano a Natale?", "data_calcola")
f("Che giorno della settimana era il 3 marzo 1990?", "data_calcola")
f("Quanti anni ha chi è nato nel 1987?", "data_calcola", "calcola")
# ── timer, promemoria, agenda ──
f("Metti un timer di dodici minuti", "timer_imposta")
f("Tymer di cinque minuti", "timer_imposta")
f("Fai partire il conto alla rovescia per la pasta, otto minuti", "timer_imposta")
f("Anzi, facciamo dodici", "timer_imposta", prima="Metti un timer di dieci minuti",
  recenti=("timer_imposta",))
f("Ricordami domani alle nove di chiamare l'idraulico", "promemoria_imposta")
f("Tra un'ora ricordami di togliere il bucato", "promemoria_imposta")
f("Ricordami di comprare il latte", "promemoria_imposta", "lista_aggiungi")
f("Giovedì alle quattro ho la visita dal dentista", "appuntamento_aggiungi")
f("Segnami la riunione di lunedì mattina alle dieci", "appuntamento_aggiungi")
f("Cosa devo fare domani?", "appuntamenti_elenca", "agenda_elenca")
f("Ho impegni questa settimana?", "appuntamenti_elenca", "agenda_elenca")
f("Quanto manca al timer?", "agenda_elenca")
f("Togli il timer della pasta", "agenda_annulla")
f("Cancella l'appuntamento dal dentista", "agenda_annulla")
# ── liste ──
f("Aggiungi uova e farina alla spesa", "lista_aggiungi")
f("Metti il detersivo nella lista", "lista_aggiungi")
f("Cosa manca da comprare?", "lista_leggi")
f("Leggimi la lista della spesa", "lista_leggi")
f("Ho preso le uova, toglile", "lista_togli")
f("Svuota la lista della spesa", "lista_togli")
# ── memoria ──
f("Ricordati che sono allergico alle noci", "ricorda")
f("Tieni a mente che mia sorella si chiama Clelia", "ricorda")
f("Il mio colore preferito è il verde", "ricorda")
f("Scordati di quella cosa delle noci", "dimentica")
# ── persone e voci ──
f("Sai chi sono?", "chi_parla")
f("Con chi stai parlando adesso?", "chi_parla")
f("Chiamami Beppe d'ora in poi", "rinomina_interlocutore")
f("Che voci hai?", "elenca_voci")
f("Parla con un'altra voce", "cambia_voce", "elenca_voci")
f("Chi vive in questa casa?", "elenca_utenti")
f("Aggiungi mio figlio Tobia, è nato nel 2015", "registra_utente")
# ── casa ──
f("Accendi la luce in cucina", "casa_comando")
f("Accendi la lucina cucina", "casa_comando")
f("Spegni tutte le luci del soggiorno", "casa_comando")
f("Abbassa le tapparelle della camera", "casa_comando")
f("Metti il riscaldamento a ventuno gradi", "casa_comando")
f("E in camera?", "casa_comando", prima="Accendi la luce in cucina", recenti=("casa_comando",))
f("Spegnila", "casa_comando", prima="Accendi la luce del bagno", recenti=("casa_comando",))
f("Che temperatura c'è in salotto?", "casa_stato")
f("La porta del garage è chiusa?", "casa_stato")
f("Hai il collegamento con la domotica?", "casa_integrazione", "calliope_stato")
f("Che tempo fa?", "meteo_leggi", "web_cerca")
f("Domani piove?", "meteo_leggi", "web_cerca")
f("Abito a Borgo Lieto, ricordatelo per il meteo", "citta_casa_salva", "ricorda")
# ── sapere, web, notizie ──
f("Quando è nato Garibaldi?", "biblioteca_cerca", "web_cerca")
f("Quanto è alto il Monte Bianco?", "biblioteca_cerca", "web_cerca")
f("Chi ha scritto i Promessi sposi?", "biblioteca_cerca")
f("Cos'è la fotosintesi?", "biblioteca_cerca")
f("Chi ha vinto la partita ieri sera?", "web_cerca", "notizie")
f("A che ora chiude il supermercato?", "web_cerca")
f("Quanto costa la benzina oggi?", "web_cerca")
f("Come si toglie una macchia di vino dal divano?", "web_cerca")
f("Ci sono novità dal mondo?", "notizie")
f("Dimmi le ultime notizie di economia", "notizie")
f("Cosa dicono i giornali sulle elezioni?", "notizie", "web_cerca")
# ── PC ──
f("Alza il volume del computer", "pc_volume")
f("Più forte", "pc_volume", prima="Alza il volume del computer", recenti=("pc_volume",))
f("Metti in pausa la musica", "pc_media")
f("Passa alla canzone dopo", "pc_media")
f("Abbassa la luminosità dello schermo", "pc_luminosita")
f("Apri la calcolatrice sul portatile", "pc_apri_app")
f("Blocca il computer", "pc_blocca")
f("Trova la bolletta del gas sul PC", "pc_cerca_file", "archivio_cerca")
f("Apri il secondo", "pc_apri_file", prima="Trova i file del preventivo",
  recenti=("pc_cerca_file",))
f("Quanta batteria ha il portatile?", "pc_stato")
f("Cosa sta suonando?", "pc_stato")
f("Guarda cosa c'è sul mio schermo", "pc_guarda")
f("Com'è questo vestito? Guardami con la webcam", "pc_guarda")
# ── documenti, ufficio, archivio ──
f("Scrivimi una lettera di disdetta della palestra", "documento_crea", "lavoro_affida")
f("Prepara un documento con la ricetta del tiramisù", "documento_crea")
f("Cambia la data della lettera in venti ottobre", "documento_modifica")
f("Cosa c'è scritto nel documento che mi hai fatto?", "documento_leggi")
f("Fai una fattura a Rossi Impianti per trecento euro", "modello_compila")
f("Preparami un preventivo per la ditta Verdi", "modello_compila", "lavoro_affida")
f("Che partita IVA ha Bianchi Forniture?", "anagrafica_cerca")
f("Aggiungi in rubrica il fornitore Neri, telefono tre tre tre", "anagrafica_salva")
f("Quando scade l'assicurazione della macchina?", "archivio_scadenze", "archivio_cerca")
f("Cosa devo pagare questo mese?", "archivio_scadenze")
f("Quanto abbiamo speso di luce quest'anno?", "archivio_somma")
f("Trova il contratto dell'affitto", "archivio_cerca", "pc_cerca_file")
f("La garanzia della lavatrice è ancora valida?", "archivio_cerca", "archivio_scadenze")
# ── agenti, sviluppo, estensioni ──
f("Fammi una relazione di dieci pagine sulle energie rinnovabili", "lavoro_affida")
f("A che punto è la relazione?", "lavoro_stato")
f("Ferma il lavoro dell'agente", "lavoro_annulla")
f("E cosa ha trovato alla fine?", "lavoro_risultato", prima="A che punto è la ricerca?",
  recenti=("lavoro_stato",))
f("Il cliente si chiama Gialli", "lavoro_rispondi", prima="A che punto è il preventivo?",
  recenti=("lavoro_stato",))
f("Rilancia il programma di prima e fammi vedere l'uscita", "programma_esegui")
f("Voglio un'estensione che mi dice il cambio euro dollaro", "sviluppo_apri")
f("Scrivimi un programma che ordina i numeri", "sviluppo_apri", "lavoro_affida")
f("Passa alla fase di collaudo", "sviluppo_passo", recenti=("sviluppo_apri",))
f("Provala con Bergamo", "sviluppo_collauda", recenti=("sviluppo_passo",))
f("Perché il collaudo ha dato zero?", "sviluppo_chiedi", recenti=("sviluppo_collauda",))
f("Correggilo tu", "sviluppo_correggi", recenti=("sviluppo_collauda",))
f("Quali estensioni abbiamo?", "estensione_gestisci")
f("Disattiva l'estensione del meteo marino", "estensione_gestisci")
# ── schermi, foto, file ──
f("Fammelo vedere sullo schermo", "schermo_mostra", prima="Leggimi la lista della spesa",
  recenti=("lista_leggi",))
f("Abbina il televisore del salotto", "schermo_gestisci")
f("Cancella le mie schede dal telefono", "schede_pulisci")
f("E nella seconda foto cosa c'è?", "immagine_guarda", prima="Cosa vedi in questa foto?")
f("Archivia questa bolletta", "immagine_archivia", "allegato_archivia")
f("Leggimi la pagina tre del file", "allegato_leggi")
f("Tieni i file che ti ho mandato", "cassetto_gestisci")
# ── conversazione e dialogo ──
f("Ricominciamo da capo", "conversazione_nuova", "argomento")
f("Cosa ti avevo chiesto stamattina?", "conversazione_cerca", "stanza_cerca")
f("Dimentica tutte le nostre conversazioni", "conversazioni_dimentica")
f("Sì, fallo pure", "proposta_rispondi", prima="Apri il file del preventivo")
f("No, lascia stare", "proposta_rispondi")
f("Cambiamo discorso: parlami di Saturno", "argomento", "biblioteca_cerca")
# ── minori, esercizi ──
f("Posso giocare a un gioco nuovo?", "richiesta_tutore")
f("Aiutami con i compiti di matematica", "compiti_aiuto", "esercizi")
f("Dammi degli esercizi sulle frazioni", "esercizi")
f("Tobia può guardare la tele fino alle nove", "minore_gestisci")
# ── Calliope, installazioni, dati ──
f("Cosa sai fare?", "calliope_stato")
f("Perché non funziona il meteo?", "calliope_stato")
f("Scarica la biblioteca completa", "installa_proponi")
f("A che punto è il download?", "installa_gestisci")
f("Vai, installala", "installa_avvia", prima="Scarica la voce di Paola",
  recenti=("installa_proponi",))
f("Quali dati tieni su di me?", "dati_conservati")
# ── stanza e conoscenti ──
f("Abbiamo ospiti, smetti di ascoltare", "stanza_pausa")
f("Di cosa parlavamo prima a tavola?", "stanza_cerca", "conversazione_cerca")
f("Chi conosci oltre a noi?", "conoscenti")
f("Marco adesso è di famiglia", "conoscente_livello")
# ── senza tool: chiacchiere e cultura generale ──
f("Raccontami una barzelletta")
f("Come stai oggi?")
f("Grazie mille, sei gentilissima")
f("Oggi è proprio una bella giornata")
f("Che ne pensi della pizza con l'ananas?")
f("Dimmi una parola che fa rima con cuore")
f("Mi annoio, cosa posso fare?")
f("Buongiorno Calliope")
f("Sai cantare?")
f("Inventami una storia breve su un drago")
f("Come si dice gatto in inglese?")
f("Ordinami una pizza margherita")
f("Chiamami un taxi")
f("Disattiva l'allarme")

CASI = C
