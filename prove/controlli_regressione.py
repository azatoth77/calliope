"""Controlli sulle risposte del banco di regressione (prove/prova_regressione.py), in un modulo a
parte perché si provano a secco (prove/prova_controlli_regressione.py): il banco importato
lancerebbe il modello.
"""

import re

# Un ruolo dato come nome nella risposta: «Vuoi che ti chiami Amministratore?», «ti chiamo il
# padrone di casa» (15/10)
_RUOLO = r"(?:amministr|chi amministra|padron|propriet|mamm|pap[aà]\b)"
RUOLO_COME_NOME = re.compile(r"\bchiam\w*\s+(?:l'|il |la )?" + _RUOLO, re.I)
# Il rifiuto detto non è un ruolo dato come nome (17/10, #70, 26B sulla DGX: «non posso
# chiamarti amministratore perché è un ruolo e non un nome», giusto, contato sbagliato 2 su 3).
# Revisione della PR #140: la negazione vale solo in un'affermazione. Restano errori la domanda
# («Perché non ti chiamo papà?») e il ruolo detto dopo con «ma» («Non ti chiamerò
# Amministratore ma Papà»), e si guardano tutte le occorrenze
_NEGATO = re.compile(r"\bnon\s+(?:(?:posso|potrei|devo|voglio|ti|lo|la)\s+)*$", re.I)
_MA_RUOLO = re.compile(r"\bma\s+(?:l'|il |la )?" + _RUOLO, re.I)


def ruolo_come_nome(r: str) -> bool:
    for m in RUOLO_COME_NOME.finditer(r):
        if not _NEGATO.search(r[:m.start()]):
            return True
        dopo = r[m.end():]
        fine = re.search(r"[.!?]", dopo)
        resto = dopo[:fine.start()] if fine else dopo
        # Una domanda subito dopo il ruolo, senza un'altra frase in mezzo («Perché non ti
        # chiamo papà?»; non «Non posso chiamarti papà, ma come ti chiami?»)
        if fine is not None and fine.group() == "?" and not re.search(r"[,;:]", resto):
            return True
        if _MA_RUOLO.search(resto):
            return True
    return False


# «Calliope di Michisono.» («chi sono?» storpiato): il nome di chi parla, oppure una domanda di
# chiarimento (17/10, #70, decisione di chi amministra al passo 6). Non una risposta sulla
# ricerca della parola storpiata («non ho trovato Michisono nella biblioteca…»), anche se finisce
# con «?»; la ricerca stessa è un tool vietato nel caso
_CHIARIMENTO = re.compile(r"non (?:ho|l'ho) (?:capito|sentito)|puoi ripetere|me lo ripeti|"
                          r"ripetimelo|mi ridici|cosa intendi|che cosa intendi|intendevi|"
                          r"volevi (?:dire|chiedere)|vuoi dire|non sono sicura di", re.I)
_RICERCA = re.compile(r"biblioteca|ho cercato|non ho trovato|informazioni su|"
                      r"non (?:conosco|trovo)", re.I)


def garbato_ok(r: str, nome: str = "Dario") -> bool:
    if re.search(r"\bti chiamo\b", r, re.I) or _RICERCA.search(r):
        return False
    return (bool(re.search(rf"\b{re.escape(nome)}\b", r, re.I))
            or ("?" in r and bool(_CHIARIMENTO.search(r))))
