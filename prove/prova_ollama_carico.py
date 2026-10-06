import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

"""Prova a secco dei modelli residenti in Ollama (06/10, prova e2e sulla DGX: voce, guardiano,
rilevatore di pericolo ed embedding su un Ollama che ne tiene 3; il primo embedding scacciava
il guardiano o la voce, turni di minori e ospiti da 10–17 s). calliope/ollama_carico.py e
l'archivio delle conversazioni (calliope/conversazioni.py):

- limite letto dalla configurazione, dalla variabile, altrimenti 3 «assunto»;
- modelli usati per Ollama (distinti) e avviso solo quando sono più del limite; il registro
  delle capacità lo dice all'avvio (check_llm, con un httpx finto);
- vettori dei turni: mai durante una conversazione con il modello scarico; da inattiva a lotti
  con keep_alive 0; con il modello già caricato anche prima; la ricerca va per parole con
  Ollama pieno, per significato con un posto libero (keep_alive breve).

Niente rete: /api/ps e l'embedder sono finti."""

import tempfile
import time

import numpy as np

from calliope import ollama_carico as OC
from calliope.config import Config
from calliope.conversazione import Conversazione, turni
from calliope.conversazioni import ArchivioConversazioni, Embedder

errori = 0


def verifica(nome, cond, info=""):
    global errori
    errori += not cond
    print(f"{'ok ' if cond else 'ERR'} {nome}" + (f"  {info}" if info and not cond else ""))


URL = "http://127.0.0.1:11434"
RESIDENTI = {"v": ["gemma4:26b-a4b-it-qat", "llama-guard3:8b", "gemma4:e4b-it-qat"]}
OC.residenti = lambda url, timeout=1.0, fresca=False: (None if RESIDENTI["v"] is None
                                                          else list(RESIDENTI["v"]))


def cfg_dgx(**kw):
    c = Config()
    c.llm_backend, c.llm_native_url, c.llm_model = "ollama", URL, "gemma4:26b-a4b-it-qat"
    c.guardiano_modello, c.guardiano_pericolo_modello = "llama-guard3:8b", "gemma4:e4b-it-qat"
    c.conversazioni_embedding = "qwen3-embedding:0.6b"
    for k, v in kw.items():
        setattr(c, k, v)
    return c


def prova_limite_e_avviso():
    print("── limite e avviso ──")
    os.environ.pop("OLLAMA_MAX_LOADED_MODELS", None)
    OC.dimentica_cache()
    c = cfg_dgx()
    if not sys.platform.startswith("linux"):
        verifica("limite non leggibile: 3, assunto", OC.limite(c) == (3, "assunto"))
    verifica("limite dalla configurazione", OC.limite(cfg_dgx(ollama_max_modelli=4))
             == (4, "configurazione"))
    os.environ["OLLAMA_MAX_LOADED_MODELS"] = "5"
    OC.dimentica_cache()
    verifica("limite dalla variabile", OC.limite(c) == (5, "ambiente"))
    os.environ.pop("OLLAMA_MAX_LOADED_MODELS")
    OC.dimentica_cache()
    u = OC.usati(c)
    verifica("DGX: quattro modelli sullo stesso Ollama",
             [m for _, m in u[URL]] == ["gemma4:26b-a4b-it-qat", "llama-guard3:8b",
                                        "gemma4:e4b-it-qat", "qwen3-embedding:0.6b"], str(u))
    a = OC.avviso(cfg_dgx(ollama_max_modelli=3))
    verifica("avviso: 3 contro 4, con i nomi e il passo",
             a and "al più 3 modelli" in a["frase"] and "ne usa 4" in a["frase"]
             and "OLLAMA_MAX_LOADED_MODELS=4" in a["passo"], str(a))
    if not sys.platform.startswith("linux"):
        a = OC.avviso(c)
        verifica("avviso con il limite non leggibile: lo dice (assunto)",
                 a and "assunto" in a["frase"], str(a))
    verifica("contrario: limite 4, nessun avviso", OC.avviso(cfg_dgx(ollama_max_modelli=4))
             is None)
    lap = Config()        # portatile: rilevatore = voce (e4b), quindi tre modelli
    lap.llm_backend = "ollama"
    verifica("contrario: portatile con tre modelli, nessun avviso",
             OC.avviso(lap) is None and len(OC.usati(lap).get(lap.llm_native_url.rstrip("/"),
                                                             [])) == 3, str(OC.usati(lap)))
    verifica("contrario: senza minori né embedding, uno solo",
             OC.avviso(cfg_dgx(minori_enabled=False, conversazioni_embedding="",
                               ollama_max_modelli=1)) is None)
    # Il registro delle capacità: check_llm con un httpx finto
    from calliope import capacita

    class R:
        def raise_for_status(self):
            pass

        def json(self):
            return {"models": [{"name": "gemma4:26b-a4b-it-qat", "size": 17e9}]}

    vero = capacita.importa
    capacita.importa = lambda m: type("H", (), {"get": staticmethod(lambda *a, **k: R())})
    try:
        r = capacita.check_llm(cfg_dgx(ollama_max_modelli=3))
        r2 = capacita.check_llm(cfg_dgx(ollama_max_modelli=4))
    finally:
        capacita.importa = vero
    verifica("capacità «llm»: attiva con l'avviso e il passo (all'avvio e in calliope stato)",
             r["stato"] == "attiva" and "ne usa 4" in r["motivo"]
             and "OLLAMA_MAX_LOADED_MODELS" in r["prossimo_passo"], str(r))
    verifica("contrario: capacità «llm» senza avviso col limite giusto", r2["motivo"] == "", str(r2))


class EmbOllama:
    """Come Embedder su Ollama (url, openai False), con i vettori finti e le chiamate."""
    url, openai, modello = URL, False, "qwen3-embedding:0.6b"

    def __init__(self):
        self.chiamate = []

    def vettori(self, testi, domanda=False, keep_alive="30m"):
        self.chiamate.append((len(testi), domanda, keep_alive))
        out = np.zeros((len(testi), 4), dtype=np.float32)
        for i, t in enumerate(testi):
            out[i, 0] = 1.0 if "preventivo" in t.lower() else 0.1
            out[i, 1] = 0.5
        return out / np.linalg.norm(out, axis=1, keepdims=True)

    def close(self):
        pass


def prova_archivio():
    print("── archivio delle conversazioni: vettori solo senza scacciare nessuno ──")
    emb = EmbOllama()
    tmp = tempfile.mkdtemp(prefix="calliope-carico-")
    a = ArchivioConversazioni(os.path.join(tmp, "c.db"), embedder=emb, log=lambda s: None,
                              avvia=False, inattivita_s=600, cfg=cfg_dgx(ollama_max_modelli=3))
    conv = Conversazione()
    conv.luogo = "locale"
    tt = []
    for d, r in [("Il preventivo del bagno è di 4.200 euro", "D'accordo."),
                 ("Domani ho il dentista", "Va bene.")]:
        tt += turni([{"role": "user", "content": d}, {"role": "assistant", "content": r}])
    a.archivia(conv, tt, "p-dario", "Dario", False)
    RESIDENTI["v"] = ["gemma4:26b-a4b-it-qat", "llama-guard3:8b", "gemma4:e4b-it-qat"]
    a._vettori_mancanti()
    verifica("in conversazione, Ollama pieno e modello scarico: nessun embedding",
             emb.chiamate == [] and a.conteggi()["vettori"] == 0 and a.vettori_rimandati >= 1,
             str(emb.chiamate))
    r = a.cerca("quanto era il preventivo?", "p-dario")
    verifica("ricerca con Ollama pieno: per parole, senza caricare il modello",
             r["modo"] == "parole" and emb.chiamate == [] and r["risultati"]
             and "bagno" in r["risultati"][0]["domanda"] and a.ricerche_per_parole == 1, str(r))
    # Inattiva da 10 minuti: lotti, keep_alive 0
    a.ultima_attivita = time.monotonic() - 601
    a._vettori_mancanti()
    verifica("inattiva: vettori a lotti con keep_alive 0 (il modello si scarica subito)",
             a.conteggi()["vettori"] == 2 and emb.chiamate and all(
                 k == 0 for _, _, k in emb.chiamate), str(emb.chiamate))
    # Di nuovo attiva, modello già caricato: anche subito, sempre keep_alive 0
    tt2 = turni([{"role": "user", "content": "Il preventivo della cucina è 9.000 euro"},
                 {"role": "assistant", "content": "Capito."}])
    a.archivia(conv, tt2, "p-dario", "Dario", False)
    verifica("un turno nuovo segna l'attività", not a.inattiva())
    RESIDENTI["v"] = ["gemma4:26b-a4b-it-qat", "qwen3-embedding:0.6b", "llama-guard3:8b"]
    n = len(emb.chiamate)
    a._vettori_mancanti()
    verifica("in conversazione con il modello già caricato: i vettori subito, keep_alive 0",
             a.conteggi()["vettori"] == 3 and len(emb.chiamate) == n + 1
             and emb.chiamate[-1][2] == 0, str(emb.chiamate))
    # Ricerca con un posto libero: per significato, keep_alive breve
    RESIDENTI["v"] = ["gemma4:26b-a4b-it-qat", "llama-guard3:8b"]
    r = a.cerca("quanto era il preventivo?", "p-dario")
    verifica("ricerca con un posto libero: ibrida, il modello resta poco (2m)",
             r["modo"] == "ibrida" and emb.chiamate[-1] == (1, True, "2m"), str(emb.chiamate[-1]))
    RESIDENTI["v"] = None
    r = a.cerca("quanto era il preventivo?", "p-dario")
    verifica("Ollama che non risponde: per parole", r["modo"] == "parole")
    a.close()
    # L'Embedder vero manda il keep_alive scelto
    e = Embedder(URL, "qwen3-embedding:0.6b")
    corpi = []

    class Risp:
        status_code = 200

        def raise_for_status(self):
            pass

        def json(self):
            return {"embeddings": [[1.0, 0.0]]}
    e.http.close()
    e.http = type("C", (), {"post": lambda self, url, json=None: corpi.append(json) or Risp(),
                            "close": lambda self: None})()
    e.vettori(["x"], keep_alive=0)
    verifica("Embedder: keep_alive nella richiesta a /api/embed", corpi[-1]["keep_alive"] == 0)
    verifica("configurazione: 10 minuti d'inattività, limite letto da Ollama",
             Config().conversazioni_vettori_inattivita_s == 600.0
             and Config().ollama_max_modelli == 0)


prova_limite_e_avviso()
prova_archivio()
print(f"\n{'Tutto ok' if not errori else f'{errori} errori'}")
sys.exit(1 if errori else 0)
