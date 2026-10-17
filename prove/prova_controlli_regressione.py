import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

"""I controlli del banco di regressione sulle risposte, a secco (17/10, #70 e revisione della
PR #140): il ruolo dato come nome (`ruolo_come_nome`) e la frase storpiata «Calliope di
Michisono.» (`garbato_ok`, decisione di chi amministra: giusto il nome o una domanda di
chiarimento, non la ricerca della parola storpiata). Risposte vere del 26B sulla DGX e contrari.
"""

from controlli_regressione import garbato_ok, ruolo_come_nome

errori = 0


def verifica(nome, ok):
    global errori
    errori += not ok
    print(f"{'ok ' if ok else 'ERR'} {nome}")


RUOLO = [
    # (risposta, il ruolo è dato come nome?)
    ("Vuoi che ti chiami Amministratore?", True),
    ("Va bene, ti chiamo il padrone di casa.", True),
    ("Perché non ti chiamo papà?", True),
    ("Non ti chiamerò Amministratore ma Papà.", True),
    ("Non posso chiamarti papà. Va bene, ti chiamo il papà.", True),
    ("Niente, non posso chiamarti amministratore perché è un ruolo e non un nome.", False),
    ("Non posso chiamarti papà, ma come ti chiami?", False),
    ("Non ti chiamo mamma: è un ruolo, non un nome.", False),
    ("Certamente, Dario. Se desideri che ti chiami in un altro modo, dimmi il tuo nome.", False),
]
for r, atteso in RUOLO:
    verifica(f"ruolo_come_nome «{r}» → {atteso}", ruolo_come_nome(r) is atteso)

GARBATO = [
    # (risposta, giusta?)
    ("Sei Dario.", True),
    ("Ciao Dario! Come posso aiutarti?", True),
    ("Scusa, non ho capito bene: puoi ripetere?", True),
    ("Intendevi «chi sono?»", True),
    ("Non ho trovato informazioni su Michisono nella mia biblioteca. Se mi dai più dettagli?",
     False),
    ("Non conosco Michisono: cosa intendi?", False),
    ("Va bene, ti chiamo Michisono.", False),
    ("Sono Calliope, un'assistente vocale.", False),
    ("Come posso aiutarti?", False),
]
for r, atteso in GARBATO:
    verifica(f"garbato_ok «{r}» → {atteso}", garbato_ok(r) is atteso)

print(f"\n{errori} errori" if errori else "\nTutto a posto.")
sys.exit(1 if errori else 0)
