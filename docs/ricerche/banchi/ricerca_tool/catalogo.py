"""
Catalogo di 40 tool finti ma plausibili per Calliope (ricerca del 26/09/2026).

Descrizioni nello stile di tools/builtin.py. Ogni tool ha una categoria (per
l'instradamento a due stadi e i meta-tool), qualche frase d'esempio (per il recupero
con embedding "arricchito") e un risultato finto costruito dagli argomenti.

Nessun tool fa nulla di vero: servono solo a misurare la scelta del modello.
"""

STANZE = ["soggiorno", "cucina", "camera", "cameretta", "bagno", "studio", "corridoio",
          "tutte"]
_STANZA = {"type": "string", "enum": STANZE,
           "description": "la stanza (il salotto è il soggiorno; «tutte» per tutta la casa)"}
_NIENTE = {"type": "object", "properties": {}, "required": []}


def _p(props: dict, required=()):
    return {"type": "object", "properties": props, "required": list(required)}


def T(name, cat, desc, params=None, esempi=(), risultato=None):
    return {"name": name, "cat": cat, "desc": desc, "params": params or _NIENTE,
            "esempi": list(esempi), "risultato": risultato or (lambda a: {"ok": True})}


TOOLS = [
    # ─────────────── tempo ───────────────
    T("ora_attuale", "tempo", "Restituisce l'ora locale adesso.",
      esempi=["sai l'ora esatta", "è già tardi? che ora si è fatta"],
      risultato=lambda a: {"ora": "09:47"}),
    T("data_oggi", "tempo", "Restituisce la data di oggi: giorno della settimana e data.",
      esempi=["che data è", "in che giorno della settimana siamo"],
      risultato=lambda a: {"data": "26/09/2026", "giorno": "sabato"}),
    T("calcola", "tempo",
      "Calcola un'espressione aritmetica e restituisce il risultato esatto. Usalo per "
      "qualunque conto: somme, prodotti, divisioni, percentuali, radici. Non fare i conti "
      "a mente.",
      _p({"espressione": {"type": "string",
                          "description": "l'espressione in cifre, per esempio 17*6 o 80*15/100"}},
         ["espressione"]),
      esempi=["quanto fa 23 per 9", "fammi la somma di questi numeri", "il venti per cento di cinquanta"],
      risultato=lambda a: {"espressione": a.get("espressione"), "risultato": 102}),
    # ─────────────── timer ───────────────
    T("timer_imposta", "timer",
      "Avvia un timer che suona dopo il tempo indicato. Usalo per «timer», «sveglia tra…», "
      "«avvisami tra…».",
      _p({"minuti": {"type": "integer", "description": "minuti di durata"},
          "secondi": {"type": "integer", "description": "secondi di durata, in aggiunta ai minuti"},
          "nome": {"type": "string", "description": "a cosa serve, per esempio pasta"}}),
      esempi=["conto alla rovescia di cinque minuti", "fammi suonare tra un quarto d'ora"],
      risultato=lambda a: {"ok": True, "timer": a.get("nome") or "timer", "suona_tra":
                           f"{a.get('minuti', 0)} minuti {a.get('secondi', 0)} secondi"}),
    T("timer_annulla", "timer", "Ferma e cancella un timer attivo.",
      _p({"nome": {"type": "string", "description": "quale timer; vuoto se ce n'è uno solo"}}),
      esempi=["togli il conto alla rovescia", "non serve più il timer"],
      risultato=lambda a: {"ok": True, "annullato": a.get("nome") or "timer"}),
    # ─────────────── agenda ───────────────
    T("promemoria_crea", "agenda",
      "Crea un promemoria: all'ora indicata Calliope lo ricorda a voce a chi parla. Usalo "
      "per «ricordami di…» con una cosa da fare, non per i fatti da ricordare su di sé.",
      _p({"testo": {"type": "string", "description": "cosa ricordare, breve"},
          "quando": {"type": "string", "description": "quando, a parole: «domani alle 8», «tra un'ora»"}},
         ["testo"]),
      esempi=["ricordami stasera di portare fuori la spazzatura", "fammi ricordare alle cinque di uscire"],
      risultato=lambda a: {"ok": True, "promemoria": a.get("testo"), "quando": a.get("quando")}),
    T("promemoria_elenca", "agenda", "Elenca i promemoria in attesa di chi parla.",
      esempi=["cosa mi devi ricordare", "quali promemoria ci sono"],
      risultato=lambda a: {"promemoria": [{"testo": "chiamare il dentista", "quando": "domani 8:00"}]}),
    T("calendario_eventi", "agenda",
      "Legge gli appuntamenti del calendario di famiglia per un giorno.",
      _p({"giorno": {"type": "string", "description": "oggi, domani, sabato, una data…"}}),
      esempi=["che appuntamenti ci sono sabato", "sono libero giovedì pomeriggio"],
      risultato=lambda a: {"giorno": a.get("giorno") or "oggi",
                           "eventi": [{"ora": "18:30", "titolo": "calcetto"}]}),
    # ─────────────── informazioni online ───────────────
    T("meteo", "online",
      "Previsioni del tempo (richiede internet). Senza luogo usa la città di casa.",
      _p({"luogo": {"type": "string", "description": "città; vuoto per casa"},
          "giorno": {"type": "string", "description": "oggi, domani, sabato…; vuoto per oggi"}}),
      esempi=["previsioni per il weekend", "farà caldo oggi", "nevica in montagna"],
      risultato=lambda a: {"luogo": a.get("luogo") or "casa", "giorno": a.get("giorno") or "oggi",
                           "cielo": "nuvoloso", "pioggia": "30 %", "min": 14, "max": 21}),
    T("notizie", "online", "Le notizie principali di oggi, anche su un argomento (richiede internet).",
      _p({"argomento": {"type": "string", "description": "argomento; vuoto per le principali"}}),
      esempi=["cosa è successo oggi nel mondo", "ultime notizie di politica"],
      risultato=lambda a: {"titoli": ["Titolo uno", "Titolo due"]}),
    # ─────────────── casa ───────────────
    T("luce_accendi", "casa", "Accende la luce di una stanza.",
      _p({"stanza": _STANZA}, ["stanza"]),
      esempi=["fai luce in bagno", "accendi le lampade dello studio"],
      risultato=lambda a: {"ok": True, "accesa": a.get("stanza")}),
    T("luce_spegni", "casa", "Spegne la luce di una stanza, o di tutta la casa.",
      _p({"stanza": _STANZA}, ["stanza"]),
      esempi=["buio in corridoio", "spegni le lampade"],
      risultato=lambda a: {"ok": True, "spenta": a.get("stanza")}),
    T("luce_luminosita", "casa", "Regola l'intensità della luce di una stanza, in percentuale.",
      _p({"stanza": _STANZA,
          "percentuale": {"type": "integer", "description": "da 1 a 100"}}, ["stanza", "percentuale"]),
      esempi=["luce più soffusa", "lampada al cinquanta per cento"],
      risultato=lambda a: {"ok": True, "stanza": a.get("stanza"), "percentuale": a.get("percentuale")}),
    T("tapparella_imposta", "casa", "Apre, chiude o porta a metà le tapparelle di una stanza.",
      _p({"stanza": _STANZA,
          "posizione": {"type": "string", "enum": ["apri", "chiudi", "metà"]}}, ["stanza", "posizione"]),
      esempi=["abbassa le persiane", "apri gli scuri della cucina"],
      risultato=lambda a: {"ok": True, "stanza": a.get("stanza"), "posizione": a.get("posizione")}),
    T("termostato_imposta", "casa", "Imposta la temperatura desiderata del riscaldamento.",
      _p({"gradi": {"type": "number", "description": "gradi centigradi"},
          "stanza": _STANZA}, ["gradi"]),
      esempi=["alza il riscaldamento", "voglio venti gradi in studio"],
      risultato=lambda a: {"ok": True, "gradi": a.get("gradi"), "stanza": a.get("stanza") or "tutte"}),
    T("temperatura_stanza", "casa", "Legge la temperatura misurata in una stanza.",
      _p({"stanza": _STANZA}),
      esempi=["quanti gradi ci sono in soggiorno", "è caldo in camera"],
      risultato=lambda a: {"stanza": a.get("stanza") or "soggiorno", "gradi": 20.5}),
    T("aperture_stato", "casa", "Dice quali porte e finestre di casa sono aperte.",
      esempi=["è rimasto aperto qualcosa", "ho chiuso il portone"],
      risultato=lambda a: {"aperte": ["finestra del bagno"], "porta_ingresso": "chiusa"}),
    T("allarme_inserisci", "casa",
      "Inserisce l'allarme di casa. Non esiste un tool per disinserirlo.",
      _p({"modalita": {"type": "string", "enum": ["totale", "notte"],
                       "description": "totale quando si esce, notte quando si va a dormire"}},
         ["modalita"]),
      esempi=["arma l'antifurto", "usciamo, proteggi la casa"],
      risultato=lambda a: {"ok": True, "inserito": a.get("modalita")}),
    T("allarme_stato", "casa", "Dice se l'allarme di casa è inserito e in quale modalità.",
      esempi=["l'antifurto è attivo"],
      risultato=lambda a: {"inserito": False}),
    # ─────────────── musica ───────────────
    T("musica_riproduci", "musica",
      "Fa partire la musica: un artista, un brano, un album, una playlist o un genere. Senza "
      "indicazioni riproduce la musica preferita di chi parla.",
      _p({"cosa": {"type": "string", "description": "cosa riprodurre; vuoto per la musica preferita"},
          "stanza": _STANZA}),
      esempi=["fammi ascoltare i Beatles", "voglio sentire del jazz"],
      risultato=lambda a: {"ok": True, "in_riproduzione": a.get("cosa") or "musica preferita"}),
    T("musica_pausa", "musica", "Mette in pausa o ferma la musica.",
      esempi=["ferma la canzone", "basta musica"],
      risultato=lambda a: {"ok": True}),
    T("musica_volume", "musica", "Cambia il volume della musica.",
      _p({"azione": {"type": "string", "enum": ["alza", "abbassa", "imposta"]},
          "livello": {"type": "integer", "description": "da 0 a 100, solo con imposta"}}, ["azione"]),
      esempi=["più piano", "musica più alta"],
      risultato=lambda a: {"ok": True, "volume": a.get("livello") or 50}),
    T("musica_successiva", "musica", "Passa al brano successivo.",
      esempi=["cambia brano", "avanti un pezzo"],
      risultato=lambda a: {"ok": True, "ora_suona": "Caruso, Lucio Dalla"}),
    T("musica_cosa_suona", "musica", "Dice quale brano e artista sta suonando.",
      esempi=["come si intitola questo pezzo", "di chi è questo brano"],
      risultato=lambda a: {"brano": "Futura", "artista": "Lucio Dalla"}),
    # ─────────────── biblioteca ───────────────
    T("biblioteca_cerca", "biblioteca",
      "Cerca nella biblioteca offline (Wikipedia italiana e altre fonti) e restituisce i "
      "passaggi utili. Usalo per fatti precisi: date, numeri, biografie, luoghi.",
      _p({"domanda": {"type": "string"}}, ["domanda"]),
      esempi=["cerca informazioni su Leopardi", "in che anno è caduto il muro di Berlino"],
      risultato=lambda a: {"passaggi": ["Giuseppe Garibaldi (Nizza, 1807 – Caprera, 1882) è stato un generale."]}),
    T("leggi_libro", "biblioteca", "Legge ad alta voce un libro della biblioteca, riprendendo da dove si era arrivati.",
      _p({"titolo": {"type": "string", "description": "titolo; vuoto per l'ultimo libro"}}),
      esempi=["leggimi una fiaba", "riprendi il romanzo"],
      risultato=lambda a: {"ok": True, "libro": a.get("titolo") or "Pinocchio", "capitolo": 3}),
    # ─────────────── memoria ───────────────
    T("ricorda", "memoria",
      "Salva per sempre un fatto su chi parla, da ricordare anche nelle prossime "
      "conversazioni. Usalo quando ti chiede di ricordare qualcosa o ti dice qualcosa di "
      "importante e duraturo su di sé (gusti, date, abitudini). Il fatto è una frase breve e "
      "completa, per esempio «il suo numero preferito è 47».",
      _p({"fatto": {"type": "string"}}, ["fatto"]),
      esempi=["tieni a mente che preferisco il tè", "segnati che il mio colore preferito è il blu"],
      risultato=lambda a: {"ok": True, "salvato": a.get("fatto")}),
    T("dimentica", "memoria",
      "Cancella un fatto ricordato su chi parla, quando chiede di dimenticarlo. Il parametro "
      "descrive il fatto; «tutto» li cancella tutti.",
      _p({"fatto": {"type": "string"}}, ["fatto"]),
      esempi=["scordati quello che ti ho detto sul tè", "cancella i miei dati"],
      risultato=lambda a: {"ok": True, "cancellati": 1}),
    # ─────────────── persone ───────────────
    T("chi_parla", "persone",
      "Riporta chi sta parlando con Calliope adesso: il nome e se la voce è stata "
      "riconosciuta. Usalo quando devi sapere con chi parli.",
      esempi=["mi riconosci", "con chi stai parlando"],
      risultato=lambda a: {"nome": "Dario", "riconosciuto": True}),
    T("elenca_utenti", "persone", "Elenca le persone che Calliope riconosce dalla voce.",
      esempi=["chi riconosci dalla voce", "quanti utenti ci sono"],
      risultato=lambda a: {"utenti": ["Dario", "Giulia"], "numero": 2}),
    T("rinomina_interlocutore", "persone",
      "Cambia il nome con cui Calliope chiama la persona che sta parlando adesso. Usalo "
      "quando qualcuno dice come si chiama o chiede di essere chiamato in un altro modo.",
      _p({"nome": {"type": "string"}}, ["nome"]),
      esempi=["il mio nome è Giulia", "d'ora in poi chiamami Capo"],
      risultato=lambda a: {"ok": True, "nome": a.get("nome")}),
    T("registra_utente", "persone",
      "Avvia la registrazione della voce di una persona nuova. Usalo quando qualcuno chiede "
      "di essere registrato o aggiunto.",
      _p({"nome": {"type": "string"}}, ["nome"]),
      esempi=["aggiungi un nuovo utente", "impara la voce di mio marito"],
      risultato=lambda a: {"ok": True, "nome": a.get("nome"), "frasi_necessarie": 5}),
    # ─────────────── voce ───────────────
    T("elenca_voci", "voce",
      "Elenca le voci con cui Calliope può parlare, con i nomi brevi. A voce citane al "
      "massimo tre o quattro.",
      esempi=["con quali voci puoi parlare", "fammi sentire le voci disponibili"],
      risultato=lambda a: {"voci": ["Serena", "Paola", "Aurora", "Riccardo", "Leonardo"]}),
    T("cambia_voce", "voce",
      "Cambia la voce con cui Calliope parla alla persona corrente. Il parametro voce è un "
      "nome breve, vedi elenca_voci.",
      _p({"voce": {"type": "string"}}, ["voce"]),
      esempi=["parla con una voce maschile", "metti la voce di Aurora"],
      risultato=lambda a: {"ok": True, "voce": a.get("voce")}),
    # ─────────────── messaggi ───────────────
    T("messaggio_invia", "messaggi", "Manda un messaggio scritto a una persona di famiglia.",
      _p({"destinatario": {"type": "string"}, "testo": {"type": "string"}},
         ["destinatario", "testo"]),
      esempi=["scrivi a papà", "avvisa Luca che sono in ritardo"],
      risultato=lambda a: {"ok": True, "inviato_a": a.get("destinatario")}),
    T("messaggi_leggi", "messaggi", "Legge i messaggi nuovi ricevuti da chi parla.",
      esempi=["mi ha scritto qualcuno", "leggimi gli ultimi messaggi"],
      risultato=lambda a: {"nuovi": [{"da": "Marco", "testo": "Arrivo alle otto"}]}),
    # ─────────────── liste ───────────────
    T("lista_aggiungi", "liste", "Aggiunge una o più cose a una lista (di solito la spesa).",
      _p({"elemento": {"type": "string", "description": "cosa aggiungere"},
          "lista": {"type": "string", "description": "nome della lista; vuoto per la spesa"}},
         ["elemento"]),
      esempi=["segna il detersivo", "metti il caffè nella lista"],
      risultato=lambda a: {"ok": True, "aggiunto": a.get("elemento"), "lista": a.get("lista") or "spesa"}),
    T("lista_leggi", "liste", "Legge il contenuto di una lista (di solito la spesa).",
      _p({"lista": {"type": "string", "description": "nome della lista; vuoto per la spesa"}}),
      esempi=["cosa devo comprare", "leggimi la lista"],
      risultato=lambda a: {"lista": a.get("lista") or "spesa", "elementi": ["latte", "pane"]}),
    # ─────────────── PC e file ───────────────
    T("pc_apri", "pc", "Apre un programma su uno dei PC di casa.",
      _p({"programma": {"type": "string"},
          "pc": {"type": "string", "description": "quale PC; vuoto per quello della stanza"}},
         ["programma"]),
      esempi=["avvia Excel", "apri il browser sul computer"],
      risultato=lambda a: {"ok": True, "aperto": a.get("programma")}),
    T("file_cerca", "pc", "Cerca un documento tra i file personali di chi parla.",
      _p({"nome": {"type": "string", "description": "parole del titolo o del contenuto"}}, ["nome"]),
      esempi=["cerca il documento delle vacanze", "trova la bolletta della luce"],
      risultato=lambda a: {"trovati": [{"file": "Contratto affitto 2025.pdf", "cartella": "Documenti/Casa"}]}),
]

BY_NAME = {t["name"]: t for t in TOOLS}
assert len(TOOLS) == 40, len(TOOLS)

CATEGORIE = {
    "tempo": "ora, data e calcoli",
    "timer": "timer e conti alla rovescia",
    "agenda": "promemoria e calendario",
    "online": "meteo e notizie",
    "casa": "luci, tapparelle, riscaldamento, porte e finestre, allarme",
    "musica": "musica e volume",
    "biblioteca": "biblioteca offline e lettura di libri",
    "memoria": "ricordare o dimenticare fatti su chi parla",
    "persone": "chi parla, utenti, nomi, registrazione di voci",
    "voce": "le voci di Calliope",
    "messaggi": "messaggi tra familiari",
    "liste": "lista della spesa e altre liste",
    "pc": "programmi sui PC e file personali",
}


def schema(t: dict) -> dict:
    return {"type": "function",
            "function": {"name": t["name"], "description": t["desc"], "parameters": t["params"]}}


def schemas(names) -> list[dict]:
    return [schema(BY_NAME[n]) for n in names]


# I tool di oggi (tools/builtin.py): la base realistica a 10.
OGGI = ["chi_parla", "elenca_voci", "ora_attuale", "data_oggi", "elenca_utenti", "cambia_voce",
        "rinomina_interlocutore", "registra_utente", "ricorda", "dimentica"]
# Sottoinsiemi annidati: 5 ⊂ 10 ⊂ 20 ⊂ 40. L'ordine è fisso (cache del prefisso).
S5 = ["ora_attuale", "data_oggi", "chi_parla", "ricorda", "cambia_voce"]
S10 = S5 + [n for n in OGGI if n not in S5]
S20 = S10 + ["calcola", "timer_imposta", "promemoria_crea", "meteo", "luce_accendi",
             "luce_spegni", "termostato_imposta", "musica_riproduci", "musica_pausa",
             "lista_aggiungi"]
S40 = S20 + [t["name"] for t in TOOLS if t["name"] not in S20]
SOTTOINSIEMI = {5: S5, 10: S10, 20: S20, 40: S40}
# Sempre presenti con il recupero: i tool "di identità" e i più frequenti
NUCLEO = ["ora_attuale", "data_oggi", "chi_parla", "ricorda"]


def doc(t: dict, esempi=True) -> str:
    """Testo da indicizzare per il recupero: nome, descrizione, esempi."""
    s = f"{t['name'].replace('_', ' ')}: {t['desc']}"
    if esempi and t["esempi"]:
        s += " Esempi: " + "; ".join(t["esempi"]) + "."
    return s


# ─────────────── META-TOOL: uno per categoria, con un parametro «azione» ───────────────
# Ognuno si traduce nel tool fine del catalogo (per il punteggio e per il risultato).
def _meta(name, desc, azioni: dict, extra: dict):
    """azioni: azione → (tool fine, {argomento_meta: argomento_fine})"""
    props = {"azione": {"type": "string", "enum": list(azioni)}}
    props.update(extra)
    return {"name": name, "desc": desc, "azioni": azioni,
            "params": {"type": "object", "properties": props, "required": ["azione"]}}


META = [
    _meta("orologio", "Ora, data, timer e calcoli.",
          {"ora": ("ora_attuale", {}), "data": ("data_oggi", {}),
           "calcola": ("calcola", {"espressione": "espressione"}),
           "avvia_timer": ("timer_imposta", {"minuti": "minuti", "secondi": "secondi", "nome": "nome"}),
           "annulla_timer": ("timer_annulla", {"nome": "nome"})},
          {"espressione": {"type": "string", "description": "per calcola: l'espressione in cifre"},
           "minuti": {"type": "integer"}, "secondi": {"type": "integer"},
           "nome": {"type": "string", "description": "nome del timer"}}),
    _meta("agenda", "Promemoria che Calliope ricorda a voce e calendario di famiglia.",
          {"crea_promemoria": ("promemoria_crea", {"testo": "testo", "quando": "quando"}),
           "elenca_promemoria": ("promemoria_elenca", {}),
           "eventi": ("calendario_eventi", {"quando": "giorno"})},
          {"testo": {"type": "string"}, "quando": {"type": "string"}}),
    _meta("informazioni_online", "Meteo e notizie (richiede internet).",
          {"meteo": ("meteo", {"luogo": "luogo", "giorno": "giorno"}),
           "notizie": ("notizie", {"argomento": "argomento"})},
          {"luogo": {"type": "string"}, "giorno": {"type": "string"},
           "argomento": {"type": "string"}}),
    _meta("casa", "Comanda e legge la casa: luci, tapparelle, riscaldamento, porte e finestre, allarme "
          "(non si può disinserire).",
          {"accendi_luce": ("luce_accendi", {"stanza": "stanza"}),
           "spegni_luce": ("luce_spegni", {"stanza": "stanza"}),
           "luminosita": ("luce_luminosita", {"stanza": "stanza", "valore": "percentuale"}),
           "tapparelle": ("tapparella_imposta", {"stanza": "stanza", "valore": "posizione"}),
           "riscaldamento": ("termostato_imposta", {"stanza": "stanza", "valore": "gradi"}),
           "temperatura": ("temperatura_stanza", {"stanza": "stanza"}),
           "aperture": ("aperture_stato", {}),
           "inserisci_allarme": ("allarme_inserisci", {"valore": "modalita"}),
           "stato_allarme": ("allarme_stato", {})},
          {"stanza": _STANZA,
           "valore": {"type": "string", "description": "percentuale della luce, apri/chiudi/metà "
                      "per le tapparelle, gradi per il riscaldamento, totale/notte per l'allarme"}}),
    _meta("musica", "Riproduzione della musica.",
          {"riproduci": ("musica_riproduci", {"cosa": "cosa", "stanza": "stanza"}),
           "pausa": ("musica_pausa", {}),
           "alza_volume": ("musica_volume", {}), "abbassa_volume": ("musica_volume", {}),
           "imposta_volume": ("musica_volume", {"livello": "livello"}),
           "successiva": ("musica_successiva", {}), "cosa_suona": ("musica_cosa_suona", {})},
          {"cosa": {"type": "string", "description": "artista, brano, playlist o genere"},
           "stanza": _STANZA, "livello": {"type": "integer"}}),
    _meta("biblioteca", "Biblioteca offline: cerca fatti precisi o legge un libro ad alta voce.",
          {"cerca": ("biblioteca_cerca", {"testo": "domanda"}),
           "leggi_libro": ("leggi_libro", {"testo": "titolo"})},
          {"testo": {"type": "string", "description": "la domanda o il titolo"}}),
    _meta("memoria", "Ricorda per sempre o dimentica un fatto su chi parla (gusti, date, abitudini).",
          {"ricorda": ("ricorda", {"fatto": "fatto"}), "dimentica": ("dimentica", {"fatto": "fatto"})},
          {"fatto": {"type": "string"}}),
    _meta("persone", "Chi sta parlando, chi conosci, come chiamare chi parla, registrazione di una voce nuova.",
          {"chi_parla": ("chi_parla", {}), "elenca_utenti": ("elenca_utenti", {}),
           "rinomina": ("rinomina_interlocutore", {"nome": "nome"}),
           "registra": ("registra_utente", {"nome": "nome"})},
          {"nome": {"type": "string"}}),
    _meta("voce", "Le voci con cui parla Calliope: elencarle o cambiarla.",
          {"elenca": ("elenca_voci", {}), "cambia": ("cambia_voce", {"voce": "voce"})},
          {"voce": {"type": "string"}}),
    _meta("messaggi", "Messaggi tra familiari: mandarne uno o leggere i nuovi.",
          {"invia": ("messaggio_invia", {"destinatario": "destinatario", "testo": "testo"}),
           "leggi": ("messaggi_leggi", {})},
          {"destinatario": {"type": "string"}, "testo": {"type": "string"}}),
    _meta("lista", "Liste (di solito la spesa): aggiungere o leggere.",
          {"aggiungi": ("lista_aggiungi", {"elemento": "elemento", "lista": "lista"}),
           "leggi": ("lista_leggi", {"lista": "lista"})},
          {"elemento": {"type": "string"}, "lista": {"type": "string"}}),
    _meta("computer", "PC di casa e file personali: aprire un programma o cercare un documento.",
          {"apri_programma": ("pc_apri", {"testo": "programma", "pc": "pc"}),
           "cerca_file": ("file_cerca", {"testo": "nome"})},
          {"testo": {"type": "string", "description": "programma o parole del file"},
           "pc": {"type": "string"}}),
]
META_BY_NAME = {m["name"]: m for m in META}


def meta_schema(m) -> dict:
    return {"type": "function",
            "function": {"name": m["name"], "description": m["desc"], "parameters": m["params"]}}


def meta_to_fine(name: str, args: dict):
    """(meta, argomenti) → (tool fine, argomenti fini), o (None, {}) se non valido."""
    m = META_BY_NAME.get(name)
    if not m:
        return None, {}
    az = (args or {}).get("azione")
    if az not in m["azioni"]:
        return None, {}
    fine, mapping = m["azioni"][az]
    out = {mapping[k]: v for k, v in (args or {}).items() if k in mapping}
    if name == "musica" and az in ("alza_volume", "abbassa_volume", "imposta_volume"):
        out["azione"] = {"alza_volume": "alza", "abbassa_volume": "abbassa"}.get(az, "imposta")
    return fine, out
