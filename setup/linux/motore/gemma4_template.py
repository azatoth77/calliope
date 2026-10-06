"""Modello di chat di Gemma 4 per la voce: thinking spento anche dopo il risultato di un tool.

Il chat_template.jinja ufficiale, con il thinking spento, apre il turno del modello con un
canale di pensiero vuoto («<|channel>thought\\n<channel|>»), ma solo all'inizio del turno:
dopo il risultato di un tool il modello continua lo stesso turno senza quel prefisso, e a volte
apre lui il canale e ragiona in inglese per centinaia di token (misura del 03/10 sulla DGX con
Gemma 4 26B-A4B NVFP4: 2 seconde passate su 8 dopo un tool in errore, 10–18 s di silenzio, una
volta fino al limite del contesto; vietare il token <|channel> con logit_bias non basta, il
modello lo scrive con altri token o ragiona nel testo). Questo script copia il modello del
checkpoint e aggiunge il canale vuoto anche lì. Lo usa vllm.sh (ruolo «voce»):

    python3 gemma4_template.py <chat_template.jinja del checkpoint> <file d'uscita>
"""

import sys

TAG = "{%- endif -%}"
GIUNTA = ("{%- elif not enable_thinking | default(false) -%}\n"
          "        {{- '<|channel>thought\\n<channel|>' -}}\n    ")


def corretto(testo: str) -> str:
    s = testo.rstrip()
    if GIUNTA in s:
        return s + "\n"                        # già corretto
    coda = s[-700:]
    if not s.endswith(TAG) or "if ns.prev_message_type != 'tool_response'" not in coda:
        raise ValueError("modello di chat inatteso: la fine non è quella di Gemma 4")
    ultimo = len(s) - len(TAG)
    prima = s.rfind(TAG, 0, ultimo)            # chiude «if prev_message_type != …»
    return s[:prima] + GIUNTA + s[prima:] + "\n"


if __name__ == "__main__":
    sorgente, uscita = sys.argv[1], sys.argv[2]
    with open(sorgente, encoding="utf-8") as f:
        testo = f.read()
    with open(uscita, "w", encoding="utf-8") as f:
        f.write(corretto(testo))
