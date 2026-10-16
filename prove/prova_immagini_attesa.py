import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

"""
Prova a secco: la foto in attesa della domanda e un'altra voce in mezzo (16/10, #96).

Caso vero della DGX del 15/10 sera: chi amministra manda una foto dal telefono («aspetto la
domanda»), una sua frase breve vale 0,479 (soglia 0,48) e diventa «ospite»; la conversazione
degli schermi passa all'ospite, `Schermi._scrittura_cambiata` chiama `su_fine_conversazione`
e `InAttesa.togli` toglie la foto. Alla domanda vera il modello non ha la foto e inventa una
causa.

Con l'hub degli schermi vero (`Schermi`, `Conversazioni`), `InAttesa` collegata come in
main.py e i passi veri del ciclo (`Ciclo._segna_conversazione`, `Ciclo._foto_e_file`):
  - foto → frase d'ospite → frase della stessa persona: la foto arriva (`immagini` nel turno);
  - lo stesso con un'altra persona di casa in mezzo, e con un minore dallo stesso satellite
    (che non la riceve);
contrari:
  - la frase dell'ospite non riceve mai la foto;
  - foto → «esci» della stessa persona → la foto non c'è più, e il turno dopo ha il dato
    `FOTO_PERSA` (una volta sola);
  - foto → ospite → «esci» → la foto non c'è più (la fine vera arriva anche dopo la
    sostituzione);
  - foto → scadenza di `immagini_attesa_s` (anche con l'ospite in mezzo) → non c'è più;
  - il dato `FOTO_PERSA` oltre la sua finestra non c'è; senza perdita non c'è.
"""

import tempfile
import time
import types
from pathlib import Path

from calliope.ciclo import Ciclo
from calliope.config import Config
from calliope.immagini import FOTO_PERSA, Immagine, InAttesa
from calliope.schermi import ArchivioSchermi, Schermi
from calliope.schermi import conversazione as conv_mod

ERRORI = []


def verifica(nome, ok, dettaglio=""):
    print(("ok  " if ok else "NO  ") + nome + (f"  {dettaglio}" if dettaglio else ""), flush=True)
    if not ok:
        ERRORI.append(nome)


PROFILI = {"Dario": types.SimpleNamespace(id="dario", level="amministra"),
           "Bianca": types.SimpleNamespace(id="bianca", level="familiare"),
           "Nina": types.SimpleNamespace(id="nina", level="minore")}


class Registro:
    def get(self, nome):
        return PROFILI.get(nome)


def foto(persona="dario") -> Immagine:
    return Immagine(b"\xff\xd8\xff finta", 960, 1280, fonte="telefono", persona=persona)


class Banco:
    """Hub degli schermi vero, foto in attesa collegate come in main.py, un ciclo finto con
    i due passi veri."""

    def __init__(self, attesa_s=120.0):
        tmp = Path(tempfile.mkdtemp(prefix="calliope-foto-attesa-"))
        cfg = Config()
        cfg.memory_db = str(tmp / "s.db")
        cfg.config_dir = str(tmp)
        self.hub = Schermi(cfg, ArchivioSchermi(cfg.memory_db))
        self.attesa = InAttesa(attesa_s)
        self.fini = []
        self.hub.su_fine_conversazione.append(lambda p, m: self.fini.append((p, m)))
        self.hub.su_fine_conversazione.append(self.attesa.fine_conversazione)   # main.py
        k = types.SimpleNamespace(
            s=types.SimpleNamespace(cfg=cfg, registry=Registro(), schermi=self.hub,
                                    foto_attesa=self.attesa, satelliti=None,
                                    instradamento=types.SimpleNamespace(
                                        origine=lambda: {"satellite": "telefono"})),
            speaker_ctx=types.SimpleNamespace(current_level="familiare", identified_by="voce",
                                              is_enrolling=False),
            brain=types.SimpleNamespace(vede_immagini=lambda: True),
            corsia=types.SimpleNamespace(chiave_schermi=None), rec={}, regole=[])
        k.rule = k.regole.append
        k._segna_conversazione = types.MethodType(Ciclo._segna_conversazione, k)
        k._foto_e_file = types.MethodType(Ciclo._foto_e_file, k)
        self.k = k

    def frase(self, chi=None, come="voce", livello=None):
        """Una frase detta e rivolta a Calliope: la conversazione degli schermi, poi le foto
        del turno. Restituisce (foto, contesto, rec)."""
        k = self.k
        prof = PROFILI.get(chi) if chi else None
        k.speaker_ctx.identified_by = come
        k.speaker_ctx.current_level = livello or (prof.level if prof else "ospite")
        k.rec = {}
        t = types.SimpleNamespace(scritto=None, speaker_name=chi, context="", text="")
        k._segna_conversazione(t)
        k._foto_e_file(t)
        return t.foto, t.context, k.rec

    def esci(self):
        self.hub.conversazioni.chiudi(self.k.corsia.chiave_schermi)     # _addormentati


def prova_ospite_in_mezzo():
    b = Banco()
    b.frase("Dario")
    b.attesa.metti(foto())                       # «aspetto la domanda»
    f_ospite, ctx_ospite, rec_ospite = b.frase(None, come="nessuno")
    verifica("la frase dell'ospite non riceve la foto", f_ospite == []
             and "immagini" not in rec_ospite and FOTO_PERSA not in ctx_ospite)
    verifica("l'ospite in mezzo: l'evento dice «sostituita»",
             b.fini == [("dario", conv_mod.SOSTITUITA)], b.fini)
    f, ctx, rec = b.frase("Dario")
    verifica("foto → ospite → Dario: la foto arriva al modello (immagini nel turno)",
             len(f) == 1 and len(rec.get("immagini") or []) == 1
             and "immagine_in_ingresso" in b.k.regole, rec)
    verifica("senza perdita, nessun dato «foto persa»",
             FOTO_PERSA not in ctx and "foto_persa" not in rec)
    # La frase breve di Dario presa per ospite (il caso vero: 0,479 contro 0,48)
    b = Banco()
    b.frase("Dario")
    b.attesa.metti(foto())
    b.frase(None, come="nessuno")
    b.frase("Dario", come="breve", livello="familiare")   # breve: la conversazione non riapre
    verifica("foto → ospite → frase breve di Dario: la foto arriva anche senza riaprire",
             not b.attesa.prendi("dario") and "immagini" in b.k.rec, b.k.rec)


def prova_altre_persone():
    b = Banco()
    b.frase("Dario")
    b.attesa.metti(foto())
    f_b, _, _ = b.frase("Bianca")
    verifica("un'altra persona di casa in mezzo: non riceve la foto di Dario", f_b == [])
    f, _, rec = b.frase("Dario")
    verifica("foto → Bianca → Dario: la foto arriva", len(f) == 1 and "immagini" in rec)
    b = Banco()
    b.frase("Dario")
    b.attesa.metti(foto())
    f_n, _, rec_n = b.frase("Nina")
    verifica("un minore dallo stesso satellite: niente foto dell'adulto",
             f_n == [] and "immagini" not in rec_n)
    f, _, _ = b.frase("Dario")
    verifica("foto → Nina → Dario: la foto arriva", len(f) == 1)


def prova_fine_vera():
    b = Banco()
    b.frase("Dario")
    b.attesa.metti(foto())
    b.frase("Dario")                              # prende la foto
    b.attesa.metti(foto())
    b.esci()
    verifica("«esci» di Dario: l'evento dice «fine»", ("dario", conv_mod.FINE) in b.fini, b.fini)
    f, ctx, rec = b.frase("Dario")
    verifica("foto → «esci» → Dario: la foto non c'è più", f == [] and "immagini" not in rec)
    verifica("…e il turno ha il dato «foto persa» (rec foto_persa)",
             FOTO_PERSA in ctx and rec.get("foto_persa") is True, ctx)
    _, ctx2, rec2 = b.frase("Dario")
    verifica("il dato «foto persa» una volta sola", FOTO_PERSA not in ctx2
             and "foto_persa" not in rec2)
    # Ospite in mezzo, poi «esci» (della frase presa per ospite): fine vera
    b = Banco()
    b.frase("Dario")
    b.attesa.metti(foto())
    b.frase(None, come="nessuno")
    b.esci()
    verifica("foto → ospite → «esci»: l'evento «fine» arriva anche dopo la sostituzione",
             b.fini[-1] == ("dario", conv_mod.FINE), b.fini)
    # Una seconda chiusura (nessuno è più sostituito) non ripete l'evento
    n = len(b.fini)
    b.esci()
    verifica("una seconda chiusura non ripete l'evento", len(b.fini) == n, b.fini)
    f, ctx, _ = b.frase("Dario")
    verifica("…e la foto non c'è più (con il dato «foto persa»)", f == [] and FOTO_PERSA in ctx)


def prova_scadenza():
    b = Banco(attesa_s=0.2)
    b.frase("Dario")
    b.attesa.metti(foto())
    b.frase(None, come="nessuno")
    time.sleep(0.3)
    f, ctx, rec = b.frase("Dario")
    verifica("foto → ospite → oltre immagini_attesa_s: la foto non c'è più",
             f == [] and "immagini" not in rec)
    verifica("…con il dato «foto persa»", FOTO_PERSA in ctx and rec.get("foto_persa") is True)
    a = InAttesa(60)
    a.metti(foto())
    a.togli("dario")
    verifica("dato «foto persa» oltre la sua finestra: no", not a.persa("dario", entro_s=-1))
    verifica("dato «foto persa» per un ospite: no", not a.persa(None))
    a = InAttesa(60)
    a.metti(foto())
    verifica("fine_conversazione «sostituita» non toglie, «fine» sì",
             a.fine_conversazione("dario", conv_mod.SOSTITUITA) == 0
             and a.fine_conversazione("dario", conv_mod.FINE) == 1)


if __name__ == "__main__":
    prova_ospite_in_mezzo()
    prova_altre_persone()
    prova_fine_vera()
    prova_scadenza()
    print(f"\n{'Tutto bene' if not ERRORI else 'Fallite: ' + ', '.join(ERRORI)}")
    sys.exit(1 if ERRORI else 0)
