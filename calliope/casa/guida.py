"""
Come si collega Home Assistant, detto a voce e per iscritto (tool casa_integrazione).

I testi sono fissi, qui nel codice: il modello non li inventa. Per la voce un passo o due
alla volta, adatto al punto in cui si è fermi; per iscritto tutti i passi. Niente URL letti
per intero e mai il token: si spiega dove incollarlo, non lo si chiede.

Nomi delle voci di menu verificati sulle traduzioni italiane del frontend di Home
Assistant (home-assistant-frontend 20260930.0): Profilo → scheda «Sicurezza» → «Token di
accesso a lungo termine» → «Crea token» («Copia il tuo token di accesso. Non sarà più
mostrato.»); Impostazioni → «Assistenti vocali» → scheda «Esponi» → «Esponi le entità».
"""

# Codice della diagnosi → stato per il registro delle capacità
STATI = {
    "ok": "attiva",
    "spenta": "da_configurare", "senza_indirizzo": "da_configurare",
    "senza_token": "da_configurare", "segreti_illeggibili": "da_configurare",
    "riavvio": "da_configurare", "nessuna_entita": "da_configurare",
    "mancante": "mancante",
    "in_corso": "guasta", "non_raggiunge": "guasta", "tls_nome": "guasta",
    "tls_certificato": "guasta", "tls_impronta": "guasta", "token_rifiutato": "guasta",
    "non_admin": "guasta", "agente_assente": "guasta",
}

MOTIVI = {
    "ok": "collegata",
    "spenta": "spenta in configurazione (casa_enabled)",
    "mancante": "manca la libreria websockets",
    "senza_indirizzo": "manca casa_url",
    "senza_token": "manca il token",
    "segreti_illeggibili": "il file dei segreti non si legge",
    "riavvio": "configurazione pronta, serve un riavvio",
    "in_corso": "collegamento in corso",
    "non_raggiunge": "Home Assistant non risponde",
    "tls_nome": "il certificato è intestato a un altro nome",
    "tls_certificato": "certificato non verificabile",
    "tls_impronta": "impronta del certificato cambiata",
    "token_rifiutato": "token rifiutato",
    "non_admin": "token di un utente non amministratore",
    "agente_assente": "manca l'agente di conversazione integrato",
    "nessuna_entita": "nessuna entità esposta ad Assist",
}


def _nome_cert(d: dict) -> str:
    names = d.get("nomi") or []
    if any("duckdns" in n.lower() for n in names):
        return "al tuo nome DuckDNS"
    return "a un altro nome" if not names else "a un nome, non all'indirizzo IP"


def passo(codice: str, d: dict | None = None, esempio: str = "") -> str:
    """Il prossimo passo concreto, detto a voce a chi amministra."""
    from ..capacita import comando_libreria
    d = d or {}
    if codice == "ok":
        n, a = d.get("entita", 0), d.get("aree", 0)
        stanze = (" in una stanza" if a == 1 else f" in {a} stanze") if a else ""
        return (f"Funziona: sono collegata a Home Assistant e vedo {n} dispositivi{stanze}."
                + (f" Prova a dirmi, per esempio, «{esempio}»." if esempio else ""))
    return {
        "spenta": ("La casa è spenta nelle impostazioni: in calliope.locale.yaml metti casa_enabled a true nella "
                   "sezione casa e riavviami."),
        "mancante": ("Mi manca la libreria websockets: va installata nell'ambiente di "
                     "Calliope con " + comando_libreria("websockets", "casa")
                     + ", poi riavviami."),
        "senza_indirizzo": ("Primo passo: nel file calliope.locale.yaml, accanto a calliope.yaml, nella sezione casa, scrivi alla "
                            "voce casa_url l'indirizzo di casa di Home Assistant, con https, "
                            "l'IP del Raspberry e la porta 8123. Il nome DuckDNS no: devo "
                            "restare dentro casa. Poi ti dico il passo del token."),
        "senza_token": ("Mi manca il token. In Home Assistant apri il tuo profilo, scheda "
                        "Sicurezza, e in Token di accesso a lungo termine premi Crea token e "
                        "chiamalo Calliope. Copialo subito e incollalo nel file segreti.yaml "
                        "della mia cartella, sotto home_assistant alla voce token, poi "
                        "riavviami. Non dettarmelo: va solo nel file."),
        "segreti_illeggibili": ("Il file segreti.yaml c'è, ma non riesco a leggerlo"
                                + (f" alla riga {d['riga']}" if d.get("riga") else "")
                                + ": deve avere la riga home_assistant e sotto, rientrata, "
                                  "token seguito dal token tra virgolette."),
        "riavvio": "Indirizzo e token ci sono: riavviami e mi collego a Home Assistant.",
        "in_corso": "Mi sto collegando a Home Assistant proprio ora: riprova tra qualche secondo.",
        "non_raggiunge": ("Ho indirizzo e token, ma Home Assistant non risponde. Controlla "
                          "che il Raspberry sia acceso e che io sia sulla rete di casa; se il "
                          "suo indirizzo è cambiato, correggi casa_url in calliope.locale.yaml."),
        "tls_nome": (f"Home Assistant risponde, ma il suo certificato è intestato "
                     f"{_nome_cert(d)}. Scrivi quel nome in calliope.locale.yaml alla voce "
                     f"casa_tls_nome e riavviami: continuerò a collegarmi all'indirizzo di "
                     f"casa."),
        "tls_certificato": ("Home Assistant risponde, ma non riesco a verificare il suo "
                            "certificato. Lancia la sonda, prove sonda_ha, e copia l'impronta "
                            "che stampa in calliope.locale.yaml alla voce casa_tls_impronta."),
        "tls_impronta": ("Il certificato di Home Assistant è cambiato, forse per un rinnovo. "
                         "Aggiorna casa_tls_impronta con l'impronta nuova che stampa la sonda, "
                         "oppure usa casa_tls_nome, che resta valida anche dopo i rinnovi."),
        "token_rifiutato": ("Home Assistant ha rifiutato il token: forse è stato cancellato o "
                            "copiato male. Creane uno nuovo dal tuo profilo, scheda Sicurezza, "
                            "sostituiscilo in segreti.yaml e riavviami."),
        "non_admin": ("Il token funziona, ma è di un utente che non amministra Home "
                      "Assistant, e così non vedo cosa è esposto. Crea il token con un utente "
                      "amministratore e sostituiscilo in segreti.yaml."),
        "agente_assente": ("Sono collegata, ma non trovo l'agente di conversazione integrato "
                           "di Home Assistant. Controlla in Impostazioni, Assistenti vocali, "
                           "che ci sia l'assistente Home Assistant con la lingua italiana."),
        "nessuna_entita": ("Sono collegata, ma non vedo nessun dispositivo esposto. In Home "
                           "Assistant vai in Impostazioni, Assistenti vocali, scheda Esponi, "
                           "premi Esponi le entità e scegli luci, tapparelle, termostato e "
                           "sensori."),
    }.get(codice, "Non so a che punto è il collegamento con la casa.")


def frase_familiare(codice: str) -> str:
    """Ai familiari niente dettagli su indirizzi, file e token."""
    if codice == "ok":
        return ("Il collegamento con la casa funziona: puoi chiedermi di accendere una luce "
                "o che temperatura c'è in una stanza.")
    return ("Il collegamento con la casa non è ancora attivo: chiedi a chi amministra di "
            "completarlo.")


def guida_scritta(diag: dict, url: str | None = None) -> dict:
    """La guida completa come documento (formato di calliope/documenti/formato.py)."""
    stato = diag.get("prossimo_passo") or ""
    dove = f" Oggi casa_url vale {url}." if url else ""
    return {
        "titolo": "Collegare Calliope a Home Assistant",
        "blocchi": [
            {"tipo": "paragrafo", "testo": f"A che punto siamo: {diag.get('motivo', '')}. "
                                           f"{stato}"},
            {"tipo": "titolo", "testo": "1. L'indirizzo di Home Assistant"},
            {"tipo": "paragrafo", "testo": (
                "Nel file calliope.locale.yaml (accanto a calliope.yaml, fuori da git), sezione casa, la voce casa_url è l'indirizzo di casa: "
                "https, l'IP del Raspberry e la porta 8123, per esempio "
                "https://192.168.1.10:8123. Mai il nome DuckDNS: Calliope non esce da "
                "casa." + dove)},
            {"tipo": "titolo", "testo": "2. Il certificato"},
            {"tipo": "elenco", "numerato": False, "voci": [
                "Se Home Assistant usa il certificato di DuckDNS, scrivi quel nome in "
                "casa_tls_nome (per esempio casa-mia.duckdns.org): Calliope si collega "
                "all'IP e controlla il certificato con quel nome.",
                "In alternativa, casa_tls_impronta con l'impronta SHA-256 del certificato, "
                "stampata da prove/sonda_ha.py. Va aggiornata a ogni rinnovo.",
                "Solo come ultima scelta casa_tls_verifica: false, senza verifica; Calliope "
                "lo segnala a ogni avvio.",
            ]},
            {"tipo": "titolo", "testo": "3. Il token"},
            {"tipo": "elenco", "numerato": True, "voci": [
                "In Home Assistant, con un utente amministratore, apri il profilo (il tuo "
                "nome in basso a sinistra) e la scheda Sicurezza.",
                "In Token di accesso a lungo termine premi Crea token e chiamalo Calliope.",
                "Copia subito il token: non sarà più mostrato.",
                "Incollalo nel file segreti.yaml, nella cartella di Calliope (accanto a "
                "calliope.yaml), così: una riga home_assistant: e sotto, rientrata, "
                "token: \"il token\". Il file non va in git.",
                "In alternativa, la variabile d'ambiente CALLIOPE_HA_TOKEN, che vince sul "
                "file. Mai in calliope.yaml o calliope.locale.yaml, e non dettarlo a Calliope.",
            ]},
            {"tipo": "titolo", "testo": "4. Cosa può comandare Calliope"},
            {"tipo": "elenco", "numerato": True, "voci": [
                "In Home Assistant: Impostazioni, Assistenti vocali, scheda Esponi.",
                "Premi Esponi le entità e scegli luci, tapparelle, termostato, prese e "
                "sensori. Calliope vede solo le entità esposte.",
                "Dai nomi e alias comodi da dire, e assegna le stanze: «accendi la luce "
                "della cucina» funziona se la luce è nella stanza Cucina.",
                "Serrature, allarme, cancello e porta del garage: Calliope li legge soltanto, "
                "anche se esposti.",
            ]},
            {"tipo": "titolo", "testo": "5. Prova"},
            {"tipo": "elenco", "numerato": True, "voci": [
                "Lancia python prove/sonda_ha.py: fa solo letture e stampa versione, "
                "agente e conteggi.",
                "Riavvia Calliope e chiedi «come va il collegamento con la casa?».",
                "Poi «accendi la luce della cucina» o «che temperatura c'è in camera?».",
            ]},
        ],
    }
