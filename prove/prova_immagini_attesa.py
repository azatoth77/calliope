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
            brain=types.SimpleNamespace(vede_immagini=lambda: True,
                                        end_conversation=lambda *a: None,
                                        dimentica_conversazione=lambda: None,
                                        conv=types.SimpleNamespace(chiave="persona:dario")),
            tool_ctx=types.SimpleNamespace(conversazione_nuova=False,
                                           conversazioni_dimenticate=None, conversazioni=None),
            ombra=None, last_question=None,
            corsia=types.SimpleNamespace(chiave_schermi=None), rec={}, regole=[])
        k.rule = k.regole.append
        k._contesto_azzerato = lambda: None
        for nome in ("_segna_conversazione", "_foto_e_file", "_persona_id",
                     "_foto_attesa_dimenticata", "_conversazione_nuova_chiesta",
                     "_conversazioni_dimenticate"):
            setattr(k, nome, types.MethodType(getattr(Ciclo, nome), k))
        self.k = k
        self.t = None

    def frase(self, chi=None, come="voce", livello=None):
        """Una frase detta e rivolta a Calliope: la conversazione degli schermi, poi le foto
        del turno. Restituisce (foto, contesto della foto, rec); il turno in `self.t`."""
        k = self.k
        prof = PROFILI.get(chi) if chi else None
        k.speaker_ctx.identified_by = come
        k.speaker_ctx.current_level = livello or (prof.level if prof else "ospite")
        k.speaker_ctx.current_speaker = chi
        k.rec = {}
        t = types.SimpleNamespace(scritto=None, speaker_name=chi, context="", text="",
                                  contesto_foto=None)
        k._segna_conversazione(t)
        k._foto_e_file(t)
        self.t = t
        return t.foto, t.contesto_foto or "", k.rec

    def ricominciamo(self):
        """Il modello ha chiamato conversazione_nuova (il passo vero del ciclo)."""
        self.k.tool_ctx.conversazione_nuova = True
        return self.k._conversazione_nuova_chiesta()

    def dimentica(self, persona="dario"):
        """«Dimentica le nostre conversazioni», al «sì» (il passo vero del ciclo)."""
        self.k.tool_ctx.conversazioni_dimenticate = persona
        return self.k._conversazioni_dimenticate()

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
    # Revisione della PR #113: il dato in un campo suo, non in `context` (che vuol dire
    # biblioteca: «Controllo nella biblioteca.», last_question, citazione_tolta, ricerca)
    verifica("dopo una foto persa nessun annuncio della biblioteca: `context` del turno vuoto",
             not b.t.context, b.t.context)
    import inspect
    verifica("_rispondi unisce contesto_foto al contesto del turno, come contesto_gioco",
             "contesto_foto" in inspect.getsource(Ciclo._rispondi))
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


def prova_dimentica_ricominciamo():
    """«Ricominciamo» e «dimentica» tolgono la foto in attesa senza segnarla persa (revisione
    della PR #113)."""
    b = Banco()
    b.frase("Dario")
    b.attesa.metti(foto())
    b.ricominciamo()
    f, ctx, rec = b.frase("Dario")
    verifica("foto → «ricominciamo» (conversazione_nuova) → Dario: la foto non c'è più",
             f == [] and "immagini" not in rec)
    verifica("…senza il dato «foto persa»", FOTO_PERSA not in ctx and "foto_persa" not in rec)
    b = Banco()
    b.frase("Dario")
    b.attesa.metti(foto())
    b.dimentica("dario")
    f, ctx, rec = b.frase("Dario")
    verifica("foto → «dimentica» (al sì) → Dario: la foto non c'è più",
             f == [] and "immagini" not in rec)
    verifica("…senza il dato «foto persa»", FOTO_PERSA not in ctx and "foto_persa" not in rec)
    # Una perdita segnata prima (es. «esci») e poi «dimentica»: niente dato dopo
    b = Banco()
    b.frase("Dario")
    b.attesa.metti(foto())
    b.esci()
    b.dimentica("dario")
    _, ctx, rec = b.frase("Dario")
    verifica("«esci» poi «dimentica»: la perdita si dimentica, niente dato",
             FOTO_PERSA not in ctx and "foto_persa" not in rec)
    # Contrari: «ricominciamo» di Dario non tocca la foto di Bianca; la regola breve
    # «ricominciamo» passa dallo stesso punto
    b = Banco()
    b.frase("Bianca")
    b.attesa.metti(foto("bianca"))
    b.frase("Dario")
    b.ricominciamo()
    f, _, _ = b.frase("Bianca")
    verifica("«ricominciamo» di Dario non toglie la foto di Bianca", len(f) == 1)
    import inspect
    verifica("la regola breve «ricominciamo» toglie anche lei la foto (_foto_attesa_dimenticata)",
             "_foto_attesa_dimenticata" in inspect.getsource(Ciclo._uscite))


def prova_configurazione():
    from calliope import main as main_mod
    import inspect
    cfg = Config()
    verifica("immagini_persa_s in Config (600 s di serie)", cfg.immagini_persa_s == 600.0)
    verifica("main.py passa immagini_persa_s a InAttesa",
             "immagini_persa_s" in inspect.getsource(main_mod))
    a = InAttesa(60, persa_s=0)
    a.metti(foto())
    a.togli("dario")
    time.sleep(0.01)
    verifica("immagini_persa_s 0: il dato è spento", not a.persa("dario"))


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
    prova_dimentica_ricominciamo()
    prova_configurazione()
    print(f"\n{'Tutto bene' if not ERRORI else 'Fallite: ' + ', '.join(ERRORI)}")
    sys.exit(1 if ERRORI else 0)
