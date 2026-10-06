"""
Le risposte d'errore di Home Assistant riscritte in italiano normale (01/10/2026).

L'agente integrato di HA risponde con frasi tecniche: «Mi dispiace, nell'area Taverna il
dominio light non è stato esposto.» (prova a voce del 01/10). Qui si riconosce il modello
della frase e si dice la stessa cosa a modo di Calliope: «In taverna non posso comandare
nessuna luce: non è esposta ad Assist in Home Assistant.»

I modelli sono quelli veri delle risposte d'errore italiane di HA (repository
home-assistant/intents, `responses/it/_common.yaml`, sezione errors; pacchetto
home-assistant-intents 2026.9.30, verificato con `get_intents("it")`). prove/prova_casa_ha.py
li confronta con il pacchetto installato, così un cambio di testo in HA si vede subito.
Codici di errore di HA (`data.code`): no_intent_match, no_valid_targets, failed_to_handle,
unknown. Una frase che non corrisponde a nessun modello resta com'è, salvo le parole
tecniche (dominio, classe, entità): allora vale una frase per codice.
"""

import re

# Copia dei modelli di HA (chiave → testo). Solo quelli che riguardano i comandi della casa.
ERRORI_HA = {
    "no_intent": "Mi dispiace, non ho capito",
    "handle_error": "Si è verificato un errore inatteso durante l'elaborazione",
    "no_area": "Mi dispiace, non conosco nessuna area chiamata {{ area }}",
    "no_floor": "Mi dispiace, non conosco nessun piano chiamato {{ floor }}",
    "no_domain": "Mi dispiace, non conosco nessun dispositivo appartenente al dominio {{ domain }}",
    "no_domain_in_area": "Mi dispiace, nell'area {{ area }} non conosco nessun dispositivo "
                         "appartenente al dominio {{ domain }}",
    "no_domain_in_floor": "Mi dispiace, nel piano {{ floor }} non conosco nessun dispositivo "
                          "appartenente al dominio {{ domain }}",
    "no_device_class": "Mi dispiace, non conosco nessun dispositivo appartenente alla classe "
                       "{{ device_class }}",
    "no_device_class_in_area": "Mi dispiace, nell'area {{ area }} non conosco nessun dispositivo "
                               "appartenente alla classe {{ device_class }}",
    "no_device_class_in_floor": "Mi dispiace, nel piano {{ floor }} non conosco nessun "
                                "dispositivo appartenente alla classe {{ device_class }}",
    "no_entity": "Mi dispiace, non conosco nessun dispositivo chiamato {{ entity }}",
    "no_entity_in_area": "Mi dispiace, nell'area {{ area }} non conosco nessun dispositivo "
                         "chiamato {{ entity }}",
    "no_entity_in_floor": "Mi dispiace, nel piano {{ floor }} non conosco nessun dispositivo "
                          "chiamato {{ entity }}",
    "entity_wrong_state": "Mi dispiace, nessun dispositivo è nello stato {{ state | lower }}",
    "feature_not_supported": "Mi dispiace, nessun dispositivo supporta le funzionalità richieste",
    "no_entity_exposed": "Mi dispiace, il dispositivo {{ entity }} non è stato esposto",
    "no_entity_in_area_exposed": "Mi dispiace, il dispositivo {{ entity }} nell'area {{ area }} "
                                 "non è stato esposto",
    "no_entity_in_floor_exposed": "Mi dispiace, il dispositivo {{ entity }} nel piano "
                                  "{{ floor }} non è stato esposto",
    "no_domain_exposed": "Mi dispiace, il dominio {{ domain }} non è stato esposto",
    "no_domain_in_area_exposed": "Mi dispiace, nell'area {{ area }} il dominio {{ domain }} non "
                                 "è stato esposto",
    "no_domain_in_floor_exposed": "Mi dispiace, nel piano {{ floor }} il dominio {{ domain }} "
                                  "non è stato esposto",
    "no_device_class_exposed": "Mi dispiace, nessun dispositivo appartenente alla classe "
                               "{{ device_class }} è stato esposto",
    "no_device_class_in_area_exposed": "Mi dispiace, nell'area {{ area }} nessun dispositivo "
                                       "appartenente alla classe {{ device_class }} è stato "
                                       "esposto",
    "no_device_class_in_floor_exposed": "Mi dispiace, nel piano {{ floor }} nessun dispositivo "
                                        "appartenente alla classe {{ device_class }} è stato "
                                        "esposto",
    "duplicate_entities": "Mi dispiace, esistono più dispositivi chiamati {{ entity }}",
    "duplicate_entities_in_area": "Mi dispiace, nell'area {{ area }} esistono più dispositivi "
                                  "chiamati {{ entity }}",
    "duplicate_entities_in_floor": "Mi dispiace, nel piano {{ floor }} esistono più dispositivi "
                                   "chiamati {{ entity }}",
    "duplicate_targets": "Mi dispiace, più di un dispositivo corrisponde alla tua richiesta",
}

# Dominio di HA → (cosa, femminile): «nessuna luce», «nessun interruttore»
_DOMINI = {
    "light": ("luce", True), "switch": ("interruttore", False), "cover": ("tapparella", True),
    "climate": ("termostato", False), "fan": ("ventilatore", False),
    "media_player": ("lettore multimediale", False), "lock": ("serratura", True),
    "sensor": ("sensore", False), "binary_sensor": ("sensore", False),
    "scene": ("scena", True), "script": ("sequenza", True), "vacuum": ("robot aspirapolvere", False),
    "valve": ("valvola", True), "water_heater": ("scaldabagno", False),
    "humidifier": ("umidificatore", False), "alarm_control_panel": ("allarme", False),
    "input_boolean": ("interruttore", False), "button": ("pulsante", False),
    "lawn_mower": ("tosaerba", False), "todo": ("lista", True),
}
# Classe (device_class) → (cosa, femminile)
_CLASSI = {
    "window": ("finestra", True), "door": ("porta", True), "garage": ("porta del garage", True),
    "garage_door": ("porta del garage", True), "gate": ("cancello", False),
    "blind": ("tapparella", True), "shutter": ("tapparella", True), "shade": ("tenda", True),
    "curtain": ("tenda", True), "awning": ("tenda da sole", True), "outlet": ("presa", True),
    "temperature": ("sensore di temperatura", False), "humidity": ("sensore di umidità", False),
    "motion": ("sensore di movimento", False), "occupancy": ("sensore di presenza", False),
    "tv": ("televisore", False), "speaker": ("altoparlante", False),
    "receiver": ("amplificatore", False), "power": ("misuratore di consumo", False),
}


def _pattern(template: str) -> re.Pattern:
    rx, last = "", 0
    for m in re.finditer(r"\{\{\s*(\w+)(?:\s*\|\s*\w+)?\s*\}\}", template):
        rx += re.escape(template[last:m.start()]) + f"(?P<{m.group(1)}>.+?)"
        last = m.end()
    rx += re.escape(template[last:])
    return re.compile(r"^\s*" + rx + r"\s*[.!]?\s*$", re.I)


# Prima i modelli più precisi: «il dispositivo X nell'area Y non è stato esposto» va
# riconosciuto prima di «il dispositivo X non è stato esposto», che lo prenderebbe intero
_PATTERNS = sorted(((k, _pattern(v)) for k, v in ERRORI_HA.items()),
                   key=lambda kv: (-ERRORI_HA[kv[0]].count("{{"), -len(ERRORI_HA[kv[0]])))


def _cosa(v: str, mappa: dict) -> tuple[str, bool]:
    return mappa.get(v.strip().lower(), ("dispositivo di quel tipo", False))


def _nessun(cosa: str, fem: bool) -> str:
    if fem:
        return ("nessun'" if cosa[:1] in "aeiou" else "nessuna ") + cosa
    return ("nessuno " if re.match(r"(s[^aeiou]|z|gn|ps|x|y)", cosa) else "nessun ") + cosa


def _stanza(area: str) -> str:
    a = area.strip()
    return a[:1].lower() + a[1:] if a[1:2].islower() or len(a) == 1 else a


def _dove(g: dict) -> str:
    if g.get("area"):
        return f"In {_stanza(g['area'])} "
    if g.get("floor"):
        floor = _stanza(g["floor"])
        return (f"Al {floor} " if floor.lower().startswith(("primo", "secondo", "terzo",
                                                              "piano", "pian"))
                else f"In {floor} ")
    return ""


def _cap(s: str) -> str:
    return s[:1].upper() + s[1:]


def _riscrivi(key: str, g: dict) -> str:
    dove = _dove(g)
    if "domain" in g or "device_class" in g:
        cosa, fem = (_cosa(g["domain"], _DOMINI) if "domain" in g
                     else _cosa(g["device_class"], _CLASSI))
        nessun = _nessun(cosa, fem)
        if key.endswith("_exposed"):
            esposta = "esposta" if fem else "esposto"
            return _cap(f"{dove}non posso comandare {nessun}: non è {esposta} ad Assist in "
                        f"Home Assistant.")
        return _cap(f"{dove}non trovo {nessun}.") if dove else f"In casa non trovo {nessun}."
    if "entity" in g:
        ent = g["entity"].strip()
        if key.endswith("_exposed"):
            return _cap(f"{dove}non posso comandare {ent}: in Home Assistant non è tra i "
                        f"dispositivi esposti ad Assist.")
        if key.startswith("duplicate"):
            return _cap(f"{dove}ci sono più dispositivi che si chiamano {ent}: dimmi quale, "
                        f"magari con la stanza.")
        return _cap(f"{dove}non trovo nessun dispositivo che si chiami {ent}.")
    if key == "no_area":
        return f"Non conosco nessuna stanza che si chiami {g['area'].strip()}."
    if key == "no_floor":
        return f"Non conosco nessun piano che si chiami {g['floor'].strip()}."
    if key == "entity_wrong_state":
        return f"Non c'è nessun dispositivo {g['state'].strip().lower()}."
    return {
        "no_intent": "Home Assistant non ha capito il comando.",
        "handle_error": "Home Assistant ha avuto un errore inatteso: il comando non è andato a "
                        "buon fine.",
        "feature_not_supported": "Quel dispositivo non sa fare questa cosa.",
        "duplicate_targets": "Più di un dispositivo corrisponde alla richiesta: dimmi quale, "
                             "magari con la stanza.",
    }.get(key, "")


# Parole che non devono arrivare a chi ascolta
_TECNICHE = re.compile(r"\b(dominio|domain|classe|device_class|entit[àa]|entity|"
                       r"appartenente)\b", re.I)
_PER_CODICE = {
    "no_valid_targets": "In Home Assistant non trovo un dispositivo esposto ad Assist che "
                        "corrisponda alla richiesta.",
    "no_intent_match": "Home Assistant non ha capito il comando.",
    "failed_to_handle": "Home Assistant ha avuto un errore inatteso: il comando non è andato "
                        "a buon fine.",
}


def riformula_errore(speech: str, codice: str | None = None) -> tuple[str, str | None]:
    """(frase per la voce, chiave del modello di HA riconosciuto o None)."""
    text = (speech or "").strip()
    for key, rx in _PATTERNS:
        m = rx.match(text)
        if m:
            out = _riscrivi(key, m.groupdict())
            if out:
                return out, key
    if not text or _TECNICHE.search(text):
        return _PER_CODICE.get(codice or "", "Home Assistant non ha eseguito il comando."), None
    return text, None
