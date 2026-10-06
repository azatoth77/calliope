"""
Richieste vocali italiane per il banco dei tool (ricerca del 26/09/2026).

Ogni richiesta: testo (come uscirebbe da Whisper, errori compresi), tipo, esiti
accettati. Un esito è una lista di chiamate attese; [] = nessun tool. Una chiamata è
(nome, {argomento: atteso}); il valore atteso è una stringa (contenuta nel valore, senza
accenti e maiuscole), un numero, una lista di alternative o "re:<regex>".

Tipi: diretta · colloquiale · asr (errore tipico di trascrizione) · senza (nessun tool
serve) · assente (serve una capacità che non c'è: nessun tool va chiamato) · ambigua ·
doppia (due tool) · seguito (con storia). «reale» = frase delle registrazioni vere
(prove/riferimenti_whisper.tsv).
"""

N = []          # niente tool
BIB = [("biblioteca_cerca", {})]


def R(testo, tipo, *esiti, storia=None, reale=False):
    return {"testo": testo, "tipo": tipo, "esiti": [list(e) for e in esiti],
            "storia": storia or [], "reale": reale}


def c(_tool, **args):
    return (_tool, args)


def storia_tool(utente, nome, args, risultato, risposta):
    """Un turno passato con una chiamata a un tool, nel formato interno."""
    return [{"role": "user", "content": utente},
            {"role": "assistant", "content": "", "tool_calls": [{"name": nome, "arguments": args}]},
            {"role": "tool", "name": nome, "content": risultato},
            {"role": "assistant", "content": risposta}]


RICHIESTE = [
    # ─────────────── tempo ───────────────
    R("Che ore sono?", "diretta", [c("ora_attuale")], reale=True),
    R("Calliope, che ore sono?", "diretta", [c("ora_attuale")], reale=True),
    R("Che ore so", "asr", [c("ora_attuale")]),
    R("Alliope, mi dici l'ora?", "asr", [c("ora_attuale")]),
    R("Che giorno è oggi?", "diretta", [c("data_oggi")], reale=True),
    R("Oggi quanti ne abbiamo, il venti o il ventuno?", "colloquiale", [c("data_oggi")]),
    R("Quanto fa diciassette per sei?", "diretta", [c("calcola", espressione=r"re:17\s*[*x×]\s*6")]),
    R("Quant'è il quindici per cento di ottanta?", "colloquiale", [c("calcola", espressione="re:15.*80|80.*15|0[.,]15")]),
    R("Dividi milleduecentocinquanta euro per quattro persone", "colloquiale",
      [c("calcola", espressione=r"re:1250\s*/\s*4")]),
    R("Quanto fa 38 più 47 più 112?", "diretta", [c("calcola", espressione="re:38.*47.*112")]),
    # ─────────────── timer ───────────────
    R("Metti un timer di dieci minuti", "diretta", [c("timer_imposta", minuti=10)]),
    R("Timer di 10 minuti per la pasta", "colloquiale", [c("timer_imposta", minuti=10, nome="pasta")]),
    R("Avvisami tra mezz'ora", "colloquiale", [c("timer_imposta", minuti=30)], [c("promemoria_crea")]),
    R("Fammi un timer di trenta secondi", "diretta", [c("timer_imposta", secondi=30)]),
    R("Metti un Tymer di un'ora e mezza", "asr", [c("timer_imposta", minuti=90)]),
    R("Annulla il timer della pasta", "diretta", [c("timer_annulla", nome="pasta")]),
    R("Ferma il timer", "diretta", [c("timer_annulla")]),
    # ─────────────── agenda ───────────────
    R("Ricordami domani alle otto di chiamare il dentista", "diretta",
      [c("promemoria_crea", testo="dentista", quando="domani")]),
    R("Ricordami di comprare il latte", "ambigua", [c("promemoria_crea", testo="latte")],
      [c("lista_aggiungi", elemento="latte")]),
    R("Che promemoria ho?", "diretta", [c("promemoria_elenca")]),
    R("Cosa ho in programma domani?", "diretta", [c("calendario_eventi", giorno="domani")]),
    R("Ho impegni stasera?", "colloquiale", [c("calendario_eventi")]),
    # ─────────────── online ───────────────
    R("Che tempo fa domani a Milano?", "diretta", [c("meteo", luogo="milano", giorno="domani")]),
    R("Che tempo fa?", "diretta", [c("meteo")]),
    R("Pioverà nel fine settimana?", "colloquiale", [c("meteo", giorno="re:sabato|domenica|weekend|fine settimana")]),
    R("Serve l'ombrello oggi?", "colloquiale", [c("meteo")]),
    R("Calliope, senti, secondo te conviene prendere l'ombrello se il cielo è nuvoloso?",
      "ambigua", N, [c("meteo")], reale=True),
    R("Ci sono novità sulla Formula 1?", "diretta", [c("notizie", argomento="formula")]),
    R("Dammi le notizie di oggi", "diretta", [c("notizie")]),
    # ─────────────── casa ───────────────
    R("Accendi la luce in cucina", "diretta", [c("luce_accendi", stanza="cucina")]),
    R("Accendi la luce in salotto", "colloquiale", [c("luce_accendi", stanza="soggiorno")]),
    R("Accendi la lucina cucina", "asr", [c("luce_accendi", stanza="cucina")]),
    R("Spegni tutte le luci", "diretta", [c("luce_spegni", stanza="tutte")]),
    R("Spegni la luce della camera da letto", "diretta", [c("luce_spegni", stanza="camera")]),
    R("Accendi la luce", "ambigua", [c("luce_accendi")], N),
    R("Abbassa la luce in soggiorno al trenta per cento", "diretta",
      [c("luce_luminosita", stanza="soggiorno", percentuale=30)]),
    R("Metti la luce dello studio al massimo", "colloquiale",
      [c("luce_luminosita", stanza="studio", percentuale=100)], [c("luce_accendi", stanza="studio")]),
    R("Chiudi le tapparelle in camera", "diretta", [c("tapparella_imposta", stanza="camera", posizione="chiudi")]),
    R("Alza le serrande del soggiorno", "colloquiale",
      [c("tapparella_imposta", stanza="soggiorno", posizione="apri")]),
    R("Porta a metà la tapparella della cucina", "diretta",
      [c("tapparella_imposta", stanza="cucina", posizione="meta")]),
    R("Metti il riscaldamento a ventuno gradi", "diretta", [c("termostato_imposta", gradi=21)]),
    R("Porta la cameretta a 19 gradi", "colloquiale", [c("termostato_imposta", gradi=19, stanza="cameretta")]),
    R("Che temperatura c'è in casa?", "diretta", [c("temperatura_stanza")]),
    R("Fa freddo in bagno?", "colloquiale", [c("temperatura_stanza", stanza="bagno")]),
    R("Ho lasciato qualche finestra aperta?", "colloquiale", [c("aperture_stato")]),
    R("La porta d'ingresso è chiusa?", "diretta", [c("aperture_stato")]),
    R("Inserisci l'allarme, stiamo uscendo", "diretta", [c("allarme_inserisci", modalita="totale")]),
    R("Attiva l'allarme per la notte", "diretta", [c("allarme_inserisci", modalita="notte")]),
    R("L'allarme è inserito?", "diretta", [c("allarme_stato")]),
    R("Disattiva l'allarme", "assente", N, [c("allarme_stato")]),
    # ─────────────── musica ───────────────
    R("Metti un po' di musica", "colloquiale", [c("musica_riproduci")]),
    R("Metti qualcosa di Lucio Dalla", "diretta", [c("musica_riproduci", cosa="dalla")]),
    R("Fammi sentire la mia playlist del mattino", "colloquiale", [c("musica_riproduci", cosa="mattino")]),
    R("Metti la musica in cucina", "diretta", [c("musica_riproduci", stanza="cucina")]),
    R("Metti in pausa la musica", "diretta", [c("musica_pausa")]),
    R("Stop alla musica", "colloquiale", [c("musica_pausa")]),
    R("Alza il volume", "diretta", [c("musica_volume", azione="alza")]),
    R("Volume al quaranta", "diretta", [c("musica_volume", livello=40)]),
    R("Passa alla prossima canzone", "diretta", [c("musica_successiva")]),
    R("Salta questa", "colloquiale", [c("musica_successiva")], N),
    R("Che canzone è questa?", "diretta", [c("musica_cosa_suona")]),
    # ─────────────── biblioteca ───────────────
    R("Cerca nella biblioteca chi era Garibaldi", "diretta", [c("biblioteca_cerca", domanda="garibaldi")]),
    R("Chi ha scritto I promessi sposi?", "senza", N, BIB, reale=True),
    R("Quanto dista la Luna dalla Terra?", "senza", N, BIB, reale=True),
    R("Qual è la capitale della Francia?", "senza", N, BIB, reale=True),
    R("Perché il cielo è azzurro?", "senza", N, BIB, reale=True),
    R("Leggimi Pinocchio", "diretta", [c("leggi_libro", titolo="pinocchio")]),
    R("Continua a leggere il libro di ieri sera", "colloquiale", [c("leggi_libro")]),
    # ─────────────── memoria ───────────────
    R("Ricordati che il mio numero preferito è quarantasette.", "diretta",
      [c("ricorda", fatto="re:47|quarantasette")], reale=True),
    R("Ricordati che sono allergico alle arachidi", "diretta", [c("ricorda", fatto="arachidi")]),
    R("Il mio compleanno è il tre marzo, segnatelo", "colloquiale", [c("ricorda", fatto="re:marzo")]),
    R("Dimentica il mio numero preferito", "diretta", [c("dimentica", fatto="numero")]),
    R("Cancella tutto quello che sai di me", "colloquiale", [c("dimentica", fatto="tutto")]),
    # ─────────────── persone e voce ───────────────
    R("Calliope, sai chi sono?", "diretta", [c("chi_parla")], reale=True),
    R("Chi ti sta parlando?", "diretta", [c("chi_parla")]),
    R("Quali persone conosci?", "diretta", [c("elenca_utenti")]),
    R("Chiamami Dario.", "diretta", [c("rinomina_interlocutore", nome="dario")], reale=True),
    R("Calliope, chiamami Dario Lipari.", "diretta", [c("rinomina_interlocutore", nome="dario lipari")],
      reale=True),
    R("Registra la voce di mia figlia Giulia", "diretta", [c("registra_utente", nome="giulia")]),
    R("Che voci hai?", "diretta", [c("elenca_voci")], reale=True),
    R("Calliope, usa la voce di Paola.", "diretta", [c("cambia_voce", voce="paola")], reale=True),
    R("Torna alla voce di Serena.", "diretta", [c("cambia_voce", voce="serena")], reale=True),
    R("Puoi cambiare voce?", "ambigua", N, [c("elenca_voci")], reale=True),
    R("calliope usa la voce di paola", "asr", [c("cambia_voce", voce="paola")]),
    # ─────────────── messaggi, liste, PC ───────────────
    R("Manda un messaggio a Marco: arrivo tra dieci minuti", "diretta",
      [c("messaggio_invia", destinatario="marco", testo="re:dieci|10")]),
    R("Scrivi alla mamma che stasera non ceno a casa", "colloquiale",
      [c("messaggio_invia", destinatario="mamma", testo="cen")]),
    R("Ho messaggi nuovi?", "diretta", [c("messaggi_leggi")]),
    R("Aggiungi il latte alla lista della spesa", "diretta", [c("lista_aggiungi", elemento="latte")]),
    R("Segna che mancano le uova", "colloquiale", [c("lista_aggiungi", elemento="uova")]),
    R("Aggiungi le uova e il pane alla lista", "diretta",
      [c("lista_aggiungi", elemento="uova"), c("lista_aggiungi", elemento="pane")]),
    R("Cosa c'è nella lista della spesa?", "diretta", [c("lista_leggi")]),
    R("Apri Spotify sul PC dello studio", "diretta", [c("pc_apri", programma="spotify")]),
    R("Trova il file della dichiarazione dei redditi", "diretta", [c("file_cerca", nome="redditi")]),
    R("Dove ho messo il PDF del contratto d'affitto?", "colloquiale", [c("file_cerca", nome="contratto")]),
    # ─────────────── conversazione senza tool ───────────────
    R("Raccontami una barzelletta.", "senza", N),
    R("Oggi è proprio una bella giornata.", "senza", N, reale=True),
    R("Dimmi tre città della Toscana.", "senza", N, BIB, reale=True),
    R("Grazie mille, sei stata gentile", "senza", N),
    R("Come stai?", "senza", N),
    R("Calliope, raccontami una curiosità sul mare.", "senza", N, BIB, reale=True),
    R("Mi consigli un nome per un gatto?", "senza", N),
    R("Ieri sera ho visto un documentario sulla storia dell'Impero romano e mi sono chiesto "
      "quanto tempo ci volesse per andare da Roma a Costantinopoli a cavallo.", "senza", N, BIB,
      reale=True),
    R("Che bel nome che hai, da dove viene?", "senza", N),
    R("E quella della Spagna?", "senza", N, BIB, reale=True),
    # ─────────────── capacità assenti ───────────────
    R("Ordina una pizza margherita", "assente", N),
    R("Chiama un taxi", "assente", N),
    R("Prenota un tavolo al ristorante per stasera", "assente", N),
    R("Accendi la televisione", "assente", N),
    # ─────────────── due tool ───────────────
    R("Che ore sono e che tempo fa?", "doppia", [c("ora_attuale"), c("meteo")]),
    R("Spegni la luce in cucina e metti un po' di musica", "doppia",
      [c("luce_spegni", stanza="cucina"), c("musica_riproduci")]),
    R("Chiudi le tapparelle in camera e inserisci l'allarme per la notte", "doppia",
      [c("tapparella_imposta", stanza="camera", posizione="chiudi"), c("allarme_inserisci", modalita="notte")]),
    R("Accendi la luce in soggiorno e in cucina", "doppia",
      [c("luce_accendi", stanza="soggiorno"), c("luce_accendi", stanza="cucina")]),
    R("Aggiungi il pane alla lista e ricordami domani di passare in farmacia", "doppia",
      [c("lista_aggiungi", elemento="pane"), c("promemoria_crea", testo="farmacia")]),
    R("Che giorno è oggi e cosa ho in programma?", "doppia",
      [c("data_oggi"), c("calendario_eventi")], [c("calendario_eventi")]),
    # ─────────────── seguiti (la storia conta) ───────────────
    R("E in camera?", "seguito", [c("luce_accendi", stanza="camera")],
      storia=storia_tool("Accendi la luce in soggiorno", "luce_accendi", {"stanza": "soggiorno"},
                         '{"ok": true, "accesa": "soggiorno"}', "Fatto, luce accesa in soggiorno.")),
    R("Più forte", "seguito", [c("musica_volume", azione="alza")],
      storia=storia_tool("Metti qualcosa di Lucio Dalla", "musica_riproduci", {"cosa": "Lucio Dalla"},
                         '{"ok": true, "in_riproduzione": "Lucio Dalla"}', "Ecco Lucio Dalla.")),
    R("E a Roma?", "seguito", [c("meteo", luogo="roma")],
      storia=storia_tool("Che tempo fa domani a Milano?", "meteo", {"luogo": "Milano", "giorno": "domani"},
                         '{"luogo": "Milano", "giorno": "domani", "cielo": "sereno", "max": 22}',
                         "Domani a Milano sarà sereno, con una massima di ventidue gradi.")),
    R("Anzi, facciamo dodici", "seguito", [c("timer_imposta", minuti=12)],
      [c("timer_annulla"), c("timer_imposta", minuti=12)],
      storia=storia_tool("Metti un timer di dieci minuti per la pasta", "timer_imposta",
                         {"minuti": 10, "nome": "pasta"}, '{"ok": true, "timer": "pasta"}',
                         "Timer di dieci minuti per la pasta avviato.")),
    R("Spegnila", "seguito", [c("luce_spegni", stanza="cucina")],
      storia=storia_tool("Accendi la luce in cucina", "luce_accendi", {"stanza": "cucina"},
                         '{"ok": true, "accesa": "cucina"}', "Luce della cucina accesa.")),
]
