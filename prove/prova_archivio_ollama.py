import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

"""Archivio dei documenti di casa a voce, con il modello della voce vero (Ollama).

L'archivio è quello dei documenti finti (prove/archivio_finto.py), letto con l'OCR finto e
l'estrattore finto (niente DGX): qui si misura solo la voce. Gli strumenti sono quelli di
Calliope sulla DGX (PC finto, documenti, schermi, agenti, archivio), così si vedono anche i
distrattori: «cerca sul computer il preventivo» resta a pc_cerca_file, una lettera a
documento_crea. Laura è familiare, Mario amministra; i documenti di Giulia (referto, carta
d'identità) a Laura non devono arrivare nemmeno nella risposta.

    python prove\\prova_archivio_ollama.py        # 2 giri
    python prove\\prova_archivio_ollama.py 1      # 1 giro
"""

import re
import tempfile
import time
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from archivio_finto import (ClienteFinto, OcrFinto, SpeakerCtx, Speakers,  # noqa: E402
                            prepara_cartella)

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ora_giusta import ora_o_tool  # noqa: E402  (03/10: l'ora giusta senza tool vale)
from calliope.archivio import Archivio, Grafo  # noqa: E402
from calliope.archivio.estrattore import Estrattore  # noqa: E402
from calliope.brain import Brain  # noqa: E402
from calliope.config import Config  # noqa: E402
from calliope.documenti import Documenti  # noqa: E402
from calliope.documenti.consegna import LocalDelivery  # noqa: E402
from calliope.tools.builtin import build_registry  # noqa: E402
from calliope.tools.spec import ToolContext  # noqa: E402
from prove.pc_finto import FakePC  # noqa: E402

GIRI = int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].isdigit() else 2
errori = 0


def verifica(nome, ok, dettaglio=""):
    global errori
    errori += not ok
    print(f"{'ok ' if ok else 'ERR'} {nome}" + (f"  {dettaglio}" if dettaglio else ""), flush=True)


def ha(*parole):
    return lambda r: all(p.lower() in r.lower() for p in parole)


def senza(*parole):
    return lambda r: not any(p.lower() in r.lower() for p in parole)


# (chi, livello, frase, tool atteso (o insieme di tool ammessi), controllo della risposta)
CASI = [
    ("Laura", "familiare", "Quanto era l'ultima bolletta della luce?", "archivio_cerca",
     ha("84,50")),
    ("Laura", "familiare", "Quanto abbiamo speso di luce nel 2025?", "archivio_somma",
     ha("97,20")),
    ("Laura", "familiare", "Quanto abbiamo speso di gas nel 2026?", "archivio_somma", ha("62,30")),
    ("Mario", "amministra", "Qual è il numero della polizza dell'auto?", "archivio_cerca",
     ha("445566")),
    ("Laura", "familiare", "Fino a quando è in garanzia la lavatrice?", "archivio_cerca",
     ha("2027")),
    ("Laura", "familiare", "Quando scade la bolletta del gas?", {"archivio_cerca", "archivio_scadenze"},
     ha("20 ottobre")),
    ("Laura", "familiare", "Quanti kilowattora c'erano nell'ultima bolletta della luce?",
     "archivio_cerca", ha("210")),
    ("Mario", "amministra", "Cosa scade nei prossimi tre mesi tra i documenti di casa?",
     "archivio_scadenze", lambda r: True),
    ("Laura", "familiare", "Quando scade la carta d'identità di Giulia?", "archivio_cerca",
     senza("2031", "14 luglio")),
    ("Mario", "amministra", "A chi è intestato il contratto di internet?", "archivio_cerca",
     ha("Mario")),
    # distrattori
    ("Mario", "amministra", "Cerca sul computer il file del preventivo.", "pc_cerca_file",
     lambda r: True),
    ("Mario", "amministra", "Preparami una lettera di disdetta per la palestra.",
     "documento_crea", lambda r: True),
    ("Laura", "familiare", "Che ore sono?", "ora_attuale", lambda r: True),
]

cfg = Config()
righe = []
prime = []
for giro in range(1, GIRI + 1):
    tmp = Path(tempfile.mkdtemp(prefix="calliope-archivio-ollama-"))
    root = tmp / "Documenti casa"
    prepara_cartella(root, tmp / "generati")
    cfg.archivio_cartella = str(root)
    cfg.archivio_intestatari = {"Mario": "Mario Bianchi", "Laura": "Laura Bianchi",
                                "Giulia": "Giulia Bianchi"}
    speakers = Speakers()
    svc = Archivio(cfg, Grafo(str(tmp / "archivio.db")), root, Estrattore(ClienteFinto(), "finto"),
                   OcrFinto(), log=lambda *a: None, profili=speakers.known_speakers)
    svc.giro()
    pc = FakePC()
    pcs = {"portatile": pc}
    docs = Documenti(cfg, str(tmp / "memoria.db"), delivery=LocalDelivery(tmp / "Documenti"),
                     pcs=pcs)
    reg = build_registry(pc=pcs, documenti=docs.formati, schermi=True, agenti=True,
                         archivio=True)
    # Per livello: i tool cambiano tra familiare e amministra, e Ollama rifarebbe il prefisso
    for chi, livello, frase, atteso, controllo in sorted(CASI, key=lambda c: c[1]):
        ctx = ToolContext(cfg=cfg, speakers=speakers, speaker_ctx=SpeakerCtx(chi, livello),
                          speaker=None, pc=pcs, documenti=docs, archivio=svc)
        b = Brain(cfg, reg, ctx)
        t0 = time.perf_counter()
        primo, parti = None, []
        for pezzo in b.stream_reply(frase, livello):
            if primo is None and pezzo.strip():
                primo = time.perf_counter() - t0
            parti.append(pezzo)
        risposta = re.sub(r"\s+", " ", "".join(parti)).strip()
        tools = [t["nome"] for t in b.last_tools]
        ammessi = atteso if isinstance(atteso, set) else {atteso}
        ok = ((bool(ammessi & set(tools)) or any(ora_o_tool(a, tools, risposta) for a in ammessi))
              and controllo(risposta))
        if primo is not None:
            prime.append(primo)
        verifica(f"[{giro}] {chi}: {frase}", ok,
                 f"{tools} → {risposta[:160]!r} ({primo or 0:.2f} s)")
    docs.close() if hasattr(docs, "close") else None
    svc.grafo.close()

prime.sort()
if prime:
    print(f"\nPrima frase: mediana {prime[len(prime) // 2]:.2f} s, massimo {prime[-1]:.2f} s")
print(f"{'Tutto bene' if not errori else f'{errori} errori'}.")
sys.exit(1 if errori else 0)
