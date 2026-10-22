"""
Prova a secco: da ospite a voce riconosciuta sullo stesso satellite (22/10/2026, issue #171).

Caso vero del 18/10 (qui con nomi di fantasia: Carlo amministra, Luca è il minore): dal telefono
in auto le prime due frasi di chi amministra non sono riconosciute (ospite); dalla terza la voce
lo riconosce, ma il modello continua a dirgli «il sistema dice che sei un ospite». I dati del
turno della terza dicevano solo «persona: Carlo, riconosciuta dalla voce», senza il cambio.

- Con le conversazioni per persona (calliope/corsie.py, il flusso vero dei satelliti): due frasi
  da ospite nella conversazione anonima del satellite, poi Carlo riconosciuto dalla voce nella
  sua conversazione → i dati del turno della terza dicono il cambio, una volta (regola
  `voce_ora_riconosciuta`); la quarta no. Le frasi da ospite restano nella conversazione
  anonima, fuori da quella di Carlo.
- Nella conversazione anonima condivisa in compagnia (passo 0 della decisione 0029): due frasi
  da ospite, poi Carlo nella stessa conversazione → il cambio e le frasi di prima marcate
  «voce non riconosciuta» (nota del gruppo).
- Contrari: Carlo riconosciuto dall'inizio (nessuna riga in più); la frase da ospite oltre
  `storia_inattiva_s`; un altro luogo; un conoscente dopo l'ospite; un ospite dopo Carlo (il
  verso inverso non ha la riga).

La prima e la seconda verifica falliscono su main (950b877).
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from calliope import corsie
from calliope.brain import Brain
from calliope.config import Config
from calliope.conversazione import Conversazione

errori = 0
CAMBIO = "Ora la voce è riconosciuta: parla Carlo."


def verifica(nome, ok, dettaglio=""):
    global errori
    errori += not ok
    print(f"{'ok ' if ok else 'ERR'} {nome}" + (f"  {dettaglio}" if dettaglio else ""),
          flush=True)


class Backend:
    def __init__(self):
        self.visti = []

    def stream(self, messages, tools):
        self.visti.append([dict(m) for m in messages])
        yield ("text", "Va bene.")


class Prof:
    def __init__(self, pid, name):
        self.id, self.name = pid, name


class Voci:
    def get(self, n):
        return {"Carlo": Prof("carlo-id", "Carlo"), "Luca": Prof("luca-id", "Luca")}.get(n)


class Chi:
    """Lo stato di chi parla (speaker_id.SpeakerContext), quanto basta a Brain."""
    current_speaker = None
    current_level = "ospite"
    identified_by = None
    compagnia, compagnia_sconosciute = False, False
    conoscente = None


def brain_finto(chiave="ospite:sat:tel"):
    from calliope.tools.builtin import build_registry
    cfg = Config()
    b = Brain.__new__(Brain)
    b.cfg, b.tools, b.history = cfg, build_registry(), []
    b.conv = Conversazione(chiave)
    chi = Chi()
    b.tool_ctx = type("T", (), {"speaker_ctx": chi, "speakers": Voci()})()
    b.backend = Backend()
    return b, chi


def dati(b) -> str:
    """I messaggi di sistema dell'ultima richiesta al modello dopo il prompt (i dati)."""
    return " ".join(m.get("content") or "" for m in b.backend.visti[-1][1:]
                    if m.get("role") == "system")


def ospite(chi):
    chi.current_speaker, chi.current_level, chi.identified_by = None, "ospite", None
    chi.conoscente = None


def carlo(chi, how="voce"):
    chi.current_speaker, chi.current_level, chi.identified_by = "Carlo", "amministra", how
    chi.conoscente = None


def di(b, testo, chi):
    return "".join(b.stream_reply(testo, chi.current_level))


def con_corsie():
    """Il flusso vero dei satelliti: una conversazione per persona, una anonima per satellite."""
    b, chi = brain_finto()
    reg = corsie.RegistroConversazioni(b.cfg)
    tel = corsie.Corsia("sat:tel", satellite_id="tel", nome="telefono", registro=reg)

    def turno(testo):
        nome = chi.current_speaker
        tel.turno(b, nome, chi.identified_by, True, testo,
                  persona_id="carlo-id" if nome == "Carlo" else None)
        return di(b, testo, chi)
    return b, chi, tel, turno


def prova_corsie():
    b, chi, tel, turno = con_corsie()
    ospite(chi)
    turno("Che tempo fa domani a Lucca?")
    anonima = b.conv
    turno("Puoi aggiungere il latte alla lista della spesa?")
    verifica("due frasi da ospite: dati del turno da ospite, senza il cambio",
             "persona: un ospite" in dati(b) and "Ora la voce è riconosciuta" not in dati(b))
    carlo(chi)
    turno("Aggiungi il latte alla lista della spesa.")
    d3 = dati(b)
    verifica("terza frase, Carlo riconosciuto: i dati del turno dicono il cambio",
             CAMBIO in d3 and "le frasi di prima" in d3.lower()
             and "persona: Carlo, riconosciuta dalla voce" in d3
             and "voce_ora_riconosciuta" in b.last_rules, d3[-400:])
    verifica("…nella conversazione di Carlo, senza le frasi da ospite",
             b.conv is not anonima and b.conv.chiave == "persona:carlo-id"
             and [m["content"] for m in b.history if m["role"] == "user"]
             == ["Aggiungi il latte alla lista della spesa."]
             and len([m for m in anonima.history if m["role"] == "user"]) == 2,
             b.conv.chiave)
    verifica("…la riga sta nei dati del turno, non nella storia",
             all(CAMBIO not in (m.get("content") or "") for m in b.history))
    turno("E anche il pane.")
    verifica("quarta frase, ancora Carlo: la riga non si ripete",
             CAMBIO not in dati(b) and "voce_ora_riconosciuta" not in b.last_rules,
             dati(b)[-300:])
    # Contrario: Carlo riconosciuto dall'inizio
    b, chi, tel, turno = con_corsie()
    carlo(chi)
    for testo in ("Che tempo fa domani?", "Aggiungi il latte.", "E anche il pane."):
        turno(testo)
        verifica(f"contrario: Carlo riconosciuto dall'inizio, «{testo}» → nessuna riga",
                 "Ora la voce è riconosciuta" not in dati(b)
                 and "voce_ora_riconosciuta" not in b.last_rules)
    # Contrario: l'ospite dopo Carlo (il verso inverso non ha la riga)
    ospite(chi)
    turno("Chi sei?")
    verifica("contrario: un ospite dopo Carlo → solo «persona: un ospite»",
             "persona: un ospite" in dati(b) and "riconosciuta" not in dati(b).split(
                 "Se ti chiedono l'ora")[0], dati(b)[:300])


def prova_condivisa():
    """La conversazione anonima condivisa in compagnia (13/10, passo 0 della decisione 0029)."""
    b, chi = brain_finto()
    chi.compagnia = True
    ospite(chi)
    di(b, "Hai preso il caricabatterie?", chi)
    di(b, "Ci fermiamo a fare benzina?", chi)
    carlo(chi, "conversazione")
    di(b, "Allora fermiamoci alla prossima.", chi)
    d3 = dati(b)
    verifica("in compagnia, nella conversazione condivisa: il cambio nei dati del turno",
             CAMBIO in d3 and "compagnia_anonima_continua" in b.last_rules
             and len([m for m in b.history if m["role"] == "user"]) == 3, d3[-500:])
    verifica("…e le frasi di prima marcate come di una voce non riconosciuta",
             "dalla più vecchia: voce non riconosciuta, voce non riconosciuta" in d3
             and [m.get("_chi") for m in b.history if m["role"] == "user"]
             == ["voce non riconosciuta", "voce non riconosciuta", "Carlo"], d3[-500:])
    di(b, "Grazie.", chi)
    verifica("…la riga non si ripete al quarto turno", CAMBIO not in dati(b))


def prova_contrari():
    # La frase da ospite è troppo vecchia (oltre storia_inattiva_s)
    b, chi, tel, turno = con_corsie()
    ospite(chi)
    turno("Che tempo fa domani?")
    prima = b._voce_prima
    b._voce_prima = (prima[0], prima[1] - b.cfg.storia_inattiva_s - 5, prima[2])
    carlo(chi)
    turno("Aggiungi il latte.")
    verifica("contrario: la frase da ospite oltre storia_inattiva_s → nessuna riga",
             CAMBIO not in dati(b))
    # Un altro luogo (un altro satellite con lo stesso Brain)
    b, chi, tel, turno = con_corsie()
    luogo = ["cucina"]
    b.luogo_fn = lambda: luogo[0]
    ospite(chi)
    turno("Che tempo fa domani?")
    luogo[0] = "studio"
    carlo(chi)
    turno("Aggiungi il latte.")
    verifica("contrario: l'ospite era in un altro luogo → nessuna riga", CAMBIO not in dati(b))
    # Lo stesso luogo: la riga c'è
    b, chi, tel, turno = con_corsie()
    b.luogo_fn = lambda: "cucina"
    ospite(chi)
    turno("Che tempo fa domani?")
    carlo(chi)
    turno("Aggiungi il latte.")
    verifica("…nello stesso luogo sì", CAMBIO in dati(b))
    # Un conoscente dopo l'ospite: resta un ospite (livello), niente riga
    b, chi, tel, turno = con_corsie()
    ospite(chi)
    turno("Che tempo fa domani?")
    chi.conoscente = {"id": "k1", "nome": "Gino Neri", "nota": "collega di Carlo"}
    di(b, "Mi senti?", chi)
    verifica("contrario: un conoscente dopo l'ospite → nessuna riga",
             "Ora la voce è riconosciuta" not in dati(b))
    # Interruttore spento
    b, chi, tel, turno = con_corsie()
    b.cfg.voce_ora_riconosciuta = False
    ospite(chi)
    turno("Che tempo fa domani?")
    carlo(chi)
    turno("Aggiungi il latte.")
    verifica("interruttore spento (voce_ora_riconosciuta: false) → nessuna riga",
             CAMBIO not in dati(b))


if __name__ == "__main__":
    t0 = time.monotonic()
    prova_corsie()
    prova_condivisa()
    prova_contrari()
    print(f"\n{errori} errori ({time.monotonic() - t0:.1f} s)")
    sys.exit(1 if errori else 0)
