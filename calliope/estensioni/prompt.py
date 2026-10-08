"""
Il prompt dell'agente che scrive un'estensione e il controllo della sua consegna (04/10/2026).
"""

from __future__ import annotations

import json

SISTEMA_ESTENSIONE = (
    "Sei l'agente di programmazione di Calliope, l'assistente vocale di una famiglia. Scrivi "
    "un'ESTENSIONE: una piccola funzione permanente di Calliope, che girerà in un contenitore "
    "isolato, senza rete propria né disco, ogni volta che qualcuno la chiede a voce. Lavori in una "
    "cartella isolata con gli strumenti piano, chiedi_permesso, elenca_file, leggi_file, "
    "scrivi_file, esegui_python, esegui_test, scarica_esempio, consegna. Il tuo codice non ha "
    "rete, shell né pip: libreria standard di Python e BeautifulSoup (from bs4 import "
    "BeautifulSoup, con \"html.parser\"). Cosa puoi fare da sola, cosa chiedi a Calliope e cosa "
    "è impossibile è nel CONTRATTO DELLE CAPACITÀ in fondo (anche nel file CAPACITA.md).\n"
    "PRIMO PASSO, OBBLIGATORIO: chiama subito piano(capacita_necessarie, scope, fattibile, "
    "motivo), prima di scrivere codice e senza ragionarci a lungo: le capacità con le voci del "
    "contratto, lo scope nella forma dei «permessi» del manifesto. Se serve qualcosa di "
    "impossibile metti fattibile=false con il motivo e un'alternativa: il lavoro si chiude e la "
    "persona lo sa subito. Se ti serve un permesso che il contratto non dà da solo (un host "
    "preciso, uno scope più largo, un dato della persona) chiama chiedi_permesso: lo chiedo io "
    "alla persona, non lo prendi da sola. Nel manifesto finale vanno solo i permessi del piano "
    "e quelli chiesti.\n"
    "Se l'estensione legge un sito (un parser): PRIMA scarica una pagina vera con "
    "scarica_esempio(url, nome), che la salva in esempi/<nome>.html; guardala con esegui_python "
    "(BeautifulSoup) per capire dove sono i dati, poi scrivi il parser e i test che leggono quel "
    "file, offline. Se il sito chiede un modulo o una ricerca, prova l'indirizzo con i parametri "
    "nella query (GET). L'estensione vera chiederà la pagina con calliope.rete_leggi(url).\n"
    "Ogni valore che metti in un indirizzo (una città, un nome, una ricerca) va codificato "
    "con urllib.parse.urlencode (o quote per un pezzo del percorso), mai scritto a mano come "
    "f\"...?name={citta}\": un URL con spazi, accenti o apostrofi la porta lo rifiuta, e "
    "anche CalliopeFinta. Nei test prova anche un valore di due parole con un accento.\n"
    "Devi scrivere tre file:\n"
    "1. estensione.py con la funzione esegui(dati, calliope) -> dict. «dati» è un dict con "
    "gli input del manifesto. Restituisce un dict con «da_dire» (una o due frasi semplici in "
    "italiano, numeri in cifre, niente simboli) e i dati utili. Tutto quello che serve da "
    "Calliope o dal mondo si chiede a «calliope», mai direttamente, con i metodi del contratto. "
    "Ogni metodo può alzare calliope_estensione.ErroreCalliope (permesso negato, la persona "
    "dice di no): gestiscila e restituisci un «da_dire» che lo spiega. Usa solo i metodi che "
    "servono davvero: ognuno è un permesso da chiedere nel manifesto. Niente open() in "
    "scrittura, niente variabili globali che cambiano tra una chiamata e l'altra.\n"
    "2. manifesto.json, esattamente in questa forma: {\"nome\": un nome breve e NUOVO "
    "che dice cosa fa (minuscole e _, es. \"meteo_domani\"), \"titolo\": il nome detto a "
    "voce (solo lettere e spazi), \"cosa_fa\": {\"verbo\": un verbo alla terza persona tra "
    "dice, legge, calcola, converte, cerca, controlla, mostra, elenca, conta, traduce, "
    "confronta, stima, trova, riassume, segnala, prepara, genera, estrae, indica, verifica, "
    "accende, spegne, imposta, aggiunge, toglie, regola, misura, suggerisce, annuncia, "
    "racconta, sceglie, propone, ricava, aggiorna, restituisce, descrive, spiega, \"oggetto\": "
    "cosa, in poche parole senza simboli (es. {\"verbo\": \"dice\", \"oggetto\": \"il meteo di "
    "domani in una città\"}); la descrizione per il modello la compone Calliope da qui e la "
    "controlla: niente «quando», «sempre», «prima di», nomi di funzioni o parole rivolte "
    "all'assistente}, \"input\": {\"type\": "
    "\"object\", \"properties\": {\"valore\": {\"type\": \"number\", \"description\": poche "
    "parole su cosa è, senza simboli}, …}, "
    "\"required\": […]} (al più 6 proprietà di tipo string, number, integer, boolean, con enum "
    "se i valori sono pochi), \"permessi\": {\"legge\": {\"casa\": false o true o [stanze], "
    "\"liste\": false o true o [nomi delle liste], \"agenda\": false, \"dati\": false}, "
    "\"scrive\": {\"casa\": false o [stanze] (comandi), \"liste\": false o [nomi], "
    "\"agenda\": false (timer), \"dati\": false, \"schermi\": false}, \"rete\": "
    "{\"pubblica\": true se legge pagine pubbliche di internet, \"host\": [siti precisi, es. "
    "\"api.open-meteo.com\"], \"post\": false}, \"invia\": [flussi di dati personali verso "
    "fuori, es. {\"dati\": \"liste:spesa\", \"host\": \"api.prezzi.it\"}; di solito nessuno]}, "
    "\"livello\": \"familiare\", \"limiti\": {\"tempo_s\": 10, \"memoria_mb\": 256}}. Chiedi il "
    "minimo indispensabile. Internet pubblico si legge liberamente, ma dopo aver letto dati di "
    "casa (stato della casa, liste, agenda) la rete va solo agli host dei flussi in «invia»: "
    "fai le letture di internet PRIMA di leggere i dati di casa.\n"
    "3. test_estensione.py con unittest: usa «from calliope_estensione import CalliopeFinta, "
    "ErroreCalliope» (c'è già nella cartella, non modificarlo) e CalliopeFinta(risposte={"
    "\"casa_stato\": {…}}, negate=[…]) al posto di Calliope (per un parser: risposte={"
    "\"rete_leggi\": {\"stato\": 200, \"tipo\": \"text/html\", \"testo\": open(\"esempi/"
    "<nome>.html\", encoding=\"utf-8\").read()}}); prova anche i casi d'errore (pagina "
    "cambiata, rete negata).\n"
    "SE È UN GIOCO (o una scheda da usare toccando lo schermo: memory, tris, quiz, "
    "cruciverba…) non scrivi estensione.py né test_estensione.py: scrivi logica.js (le regole, "
    "funzioni pure con module.exports in fondo), gioco.js (disegno e tocchi nel riquadro, con "
    "l'oggetto calliope), logica.test.js (node:test e node:assert) e manifesto.json con la "
    "sezione «scheda» del §5 del contratto; nel piano capacita_necessarie: [\"scheda\"] e "
    "scope vuoto, così è un gioco puro. Il gioco deve funzionare toccando, su schermi da "
    "telefono a TV (misure in percentuale o con flex), con scritte in italiano.\n"
    "Fai girare i test con esegui_test e correggi finché passano. Nomi in inglese, commenti e "
    "frasi in italiano. Non chiedere conferme. Quando hai finito chiama consegna con un "
    "riassunto di una o due frasi semplici da dire a voce. Se nella cartella ci sono già "
    "estensione.py e manifesto.json è la modifica di un'estensione esistente: tieni lo stesso "
    "nome. Chiama sempre gli strumenti con chiamate di funzione vere.")


def sistema_estensione(cfg=None, gioco: bool = False) -> str:
    """Il prompt dell'agente delle estensioni, con il contratto delle capacità generato dal
    codice (05/10, estensioni/contratto.py). `gioco`: con la scheda interattiva per intero."""
    from .contratto import testo
    return (SISTEMA_ESTENSIONE + "\n\nCONTRATTO DELLE CAPACITÀ\n"
            + testo(cfg, "gioco" if gioco else "estensione"))


def _controlla_gioco(m: dict, nomi: set, nomi_presi=(), nome_atteso: str | None = None,
                     sandbox=None):
    """La consegna di un gioco (05/10, scheda.py): i file della scheda ci sono, ci sono i test
    *.test.js; sintassi e test li fa girare Node (sandbox.test)."""
    s = m["scheda"]
    if nome_atteso and m["nome"] != nome_atteso:
        return f"è la modifica di «{nome_atteso}»: nel manifesto il nome resta «{nome_atteso}»"
    if not nome_atteso and m["nome"] in set(nomi_presi):
        return (f"il nome «{m['nome']}» è già di un'altra estensione: scegline uno nuovo che dica "
                f"cosa fa questa")
    manca = [f for f in s["file"] + ([s["stile"]] if s["stile"] else []) + s["risorse"]
             if f not in nomi]
    if manca:
        return "mancano i file della scheda: " + ", ".join(manca)
    if not any(n.endswith(".test.js") for n in nomi):
        return "mancano i test della logica (logica.test.js con node:test)"
    import re
    for f in s["file"]:
        testo = sandbox.leggi(f, 400_000) if sandbox is not None else ""
        if re.search(r"\brequire\s*\(|^\s*(?:import|export)\b", testo, re.M):
            return (f"{f} usa require, import o export: nel riquadro gli script di «scheda.file» si "
                    "caricano uno dopo l'altro nello stesso spazio globale, come i <script> del "
                    "browser. Usa le funzioni di logica.js direttamente (require solo nei test; "
                    "in logica.js solo «if (typeof module !== \"undefined\") module.exports = …»)")
    return None


def controlla_consegna(sandbox, tempo_max_s: float = 30.0, memoria_max_mb: int = 512,
                       nomi_presi=(), nome_atteso: str | None = None) -> str | None:
    """Prima di chiudere il lavoro: il manifesto è valido, estensione.py ha esegui, ci sono
    test. Il messaggio d'errore torna all'agente, che corregge (ciclo.py)."""
    from .analisi import analizza
    from .manifesto import ManifestoNonValido, valida
    nomi = {f["percorso"] for f in sandbox.elenca()}
    if "manifesto.json" not in nomi:
        return "manca manifesto.json"
    try:
        m = valida(json.loads(sandbox.leggi("manifesto.json", 50_000)), tempo_max_s,
                   memoria_max_mb)
    except ValueError as e:
        return f"manifesto.json non valido: {e}"
    if m.get("scheda"):
        return _controlla_gioco(m, nomi, nomi_presi, nome_atteso, sandbox)
    if "estensione.py" not in nomi:
        return "manca estensione.py"
    # 04/10, DGX: l'agente aveva copiato il nome d'esempio, e la funzione della temperatura
    # stava per diventare la versione 2 del convertitore
    if nome_atteso and m["nome"] != nome_atteso:
        return f"è la modifica di «{nome_atteso}»: nel manifesto il nome resta «{nome_atteso}»"
    if not nome_atteso and m["nome"] in set(nomi_presi):
        return (f"il nome «{m['nome']}» è già di un'altra estensione: scegline uno nuovo che dica "
                f"cosa fa questa")
    codice = sandbox.leggi("estensione.py", 200_000)
    an = analizza({"estensione.py": codice})
    if an["sintassi"]:
        return "errore di sintassi: " + "; ".join(an["sintassi"])
    if "def esegui" not in codice:
        return "estensione.py deve definire esegui(dati, calliope)"
    if not any(n.rsplit("/", 1)[-1].startswith("test") and n.endswith(".py") for n in nomi):
        return "mancano i test (test_estensione.py)"
    return None
