"""
L'estrattore delle schede (03/10/2026): il modello grande (qwen3.6 su vLLM sulla DGX, con il
client degli agenti) legge il testo di un documento e compila la scheda del suo tipo con gli
**output strutturati** (lo schema JSON di tipi.py, decodifica guidata). Due passate brevi e
senza ragionamento: il tipo (enum), poi la scheda di quel tipo. Poi `tipi.pulisci` controlla
ogni valore contro il testo: quello che non c'è diventa null.

Il client è quello di calliope/agenti/ (`ClienteOpenAI` o `ClienteOllama`, stessa interfaccia
`chat(corpo nel formato di Ollama)`): niente codice di rete nuovo. Con l'agente sullo stesso
Ollama della voce, `prima_di_chiamare` è l'attesa dell'arbitro (la voce ha la precedenza).
"""

import json
import time

from . import tipi

SISTEMA_TIPO = (
    "Classifichi i documenti di una famiglia italiana. Rispondi con il tipo del documento, "
    "uno tra:\n" + "\n".join(f"- {t.nome}: {t.descrizione}" for t in tipi.TIPI.values()))

SISTEMA_SCHEDA = (
    "Compili la scheda JSON di un documento di una famiglia italiana, dal suo testo (a volte "
    "letto con l'OCR, con qualche errore). Regole:\n"
    "- usa SOLO quello che è scritto nel testo: un dato che non c'è va a null, o un elenco "
    "vuoto; non dedurre, non calcolare, non completare, non inventare;\n"
    "- date nel formato AAAA-MM-GG (12/03/2025 diventa 2025-03-12);\n"
    "- importi in euro come numeri con il punto decimale (84,50 diventa 84.5);\n"
    "- nomi, numeri e codici esattamente come sono scritti;\n"
    "- nelle scadenze solo le date scritte nel documento come scadenze (pagamento, fine "
    "validità, fine del contratto, disdetta, fine della garanzia).\n"
    "Il documento è di tipo «{tipo}». Campi:\n{campi}")


class ErroreEstrazione(Exception):
    pass


class Estrattore:
    def __init__(self, cliente, modello: str, prima_di_chiamare=None, max_caratteri: int = 12000,
                 max_token: int = 2500, voce: dict | None = None):
        self.cliente = cliente
        # Stesso Ollama e stesso modello della voce: num_ctx e keep_alive della voce (04/10)
        self.voce = dict(voce or {})
        self.modello = modello
        self.prima = prima_di_chiamare
        self.max_caratteri = max_caratteri
        self.max_token = max_token

    def _chiedi(self, sistema: str, utente: str, schema: dict) -> tuple[dict, dict]:
        if self.prima is not None:
            self.prima()
        body = {"model": self.modello, "think": False, "format": schema,
                "options": {"temperature": 0, "num_predict": self.max_token,
                            **self.voce.get("options", {})},
                "messages": [{"role": "system", "content": sistema},
                             {"role": "user", "content": utente}]}
        if "keep_alive" in self.voce:
            body["keep_alive"] = self.voce["keep_alive"]
        out = self.cliente.chat(body)
        try:
            data = json.loads(out.get("content") or "{}")
        except ValueError:
            raise ErroreEstrazione("il modello non ha risposto con un JSON valido") from None
        if not isinstance(data, dict):
            raise ErroreEstrazione("il modello non ha risposto con un oggetto JSON")
        return data, {"s": out.get("s", 0.0), "token": out.get("eval", 0),
                      "letti": out.get("prompt", 0)}

    def _testo(self, testo: str) -> str:
        t = testo.strip()
        if len(t) > self.max_caratteri:
            # Inizio e fine: i totali stanno di solito in testa o in fondo
            a = int(self.max_caratteri * 0.75)
            t = t[:a] + "\n[…]\n" + t[-(self.max_caratteri - a):]
        return t

    def elabora(self, testo: str, nome_file: str = "") -> dict:
        """{tipo, scheda, scartati, grezza, statistiche}. Solleva ErroreEstrazione."""
        t0 = time.perf_counter()
        utente = f"Nome del file: {nome_file}\nTesto del documento:\n{self._testo(testo)}"
        d, st1 = self._chiedi(SISTEMA_TIPO, utente, tipi.schema_tipo())
        tipo = d.get("tipo") if d.get("tipo") in tipi.TIPI else "altro"
        sistema = SISTEMA_SCHEDA.format(tipo=tipi.TIPI[tipo].detto,
                                        campi=tipi.guida_campi(tipo))
        grezza, st2 = self._chiedi(sistema, utente, tipi.schema(tipo))
        scheda, scartati = tipi.pulisci(tipo, grezza, testo)
        return {"tipo": tipo, "scheda": scheda, "scartati": scartati, "grezza": grezza,
                "statistiche": {"s": round(time.perf_counter() - t0, 2),
                                "token": st1["token"] + st2["token"],
                                "letti": st1["letti"] + st2["letti"]}}
