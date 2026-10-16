import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

"""
Prova a secco del dispositivo da cui si parla (16/10/2026, issue #100, calliope/dispositivo.py).

Caso vero del 15/10 sera, dal telefono senza il portatile collegato: a «sei un computer?»
Calliope diceva di sì e prometteva la webcam (la spinta `foto_spinta_pc` in 4 turni), poi
pc_guarda falliva; su una foto di una persona diceva un nome di casa e parlava di un suo
«riconoscimento facciale» che non c'è.

- spinta IMG_PC_MSG: dal telefono con l'esecutore remoto non collegato, «usa la webcam» con
  una foto di prima → nessuna spinta; col portatile collegato (anche parlando dal telefono:
  pc_guarda lo raggiunge, ServerSatelliti.per_pc) → la spinta; collegato ma senza webcam →
  niente spinta per la webcam, sì per lo schermo; il PC di questo computer → la spinta;
- dati del turno: la riga «dispositivo:» per telefono, satellite vocale, PC, scritto e audio
  locale, col PC raggiungibile o no; contrario: senza dispositivo nessuna riga (i Brain delle
  altre prove restano com'erano), e la riga vale una risposta sola;
- Ciclo._dispositivo_turno: scritto, audio locale, telefono, satellite col PC, guasto → None;
- prompt di sistema: i volti non si riconoscono.
"""

import types

from calliope import dispositivo
from calliope.pc.remoto import RemotePCExecutor
from prove.prova_immagini import PCFinto, brain, foto

ERRORI = []


def verifica(nome, ok, dettaglio=""):
    print(f"  {'ok ' if ok else 'NO '} {nome}" + ("" if ok else f"  → {dettaglio}"))
    if not ok:
        ERRORI.append(nome)


class Coll:
    def __init__(self, esecutore=None, canale="satellite"):
        self.esecutore = esecutore
        self.canale = canale


class Server:
    """Il server dei satelliti finto: per_pc come ServerSatelliti.per_pc."""
    def __init__(self, coll):
        self.coll = coll

    def per_pc(self):
        return self.coll

    def attivo_pronto(self, sat_id=None):
        return self.coll

    def per_id(self, sid):
        return self.coll


def remoto(caps=None):
    """L'esecutore remoto: senza `caps` il solo telefono collegato (nessun esecutore)."""
    coll = Coll(None if caps is None else {"capacita": list(caps)}, "telefono")
    return RemotePCExecutor(Server(coll), "portatile")


class Chi:
    """Chi parla: Dario, proprietario del PC, riconosciuto dalla voce (come SC delle foto)."""
    def __init__(self, nome="Dario", livello="familiare", come="voce", sessione=False):
        self.current_speaker, self.current_level = nome, livello
        self.identified_by, self.from_session, self.sfida = come, sessione, None


def spinta(pcs, frase, disp=None, chi=None, proprietari=("Dario",)):
    b = brain([[("text", "Uno scontrino.")], [("text", "x")], [("text", "y")]],
              pc=pcs, immagini={"storia": "messaggio", "pc": True})
    b.cfg.pc_proprietari = list(proprietari)
    "".join(b.stream_reply("Cosa c'è qui?", "familiare", immagini=[foto()]))
    if chi is not None:
        b.tool_ctx.speaker_ctx = chi
    if disp is not None:
        b.dispositivo_turno = disp
    "".join(b.stream_reply(frase, "familiare"))
    req = b.backend.visti[-1]
    righe = [x["content"] for x in req if x["role"] == "system"
             and "pc_guarda con cosa=" in x["content"]]
    turno = [x["content"] for x in req if x["role"] == "system"
             and x["content"].startswith("Dati del turno")]
    return righe, b.rules_fired(), (turno[0] if turno else ""), b


def prova_spinta():
    tel = dispositivo.descrivi("telefono")
    righe, regole, _, _ = spinta({"portatile": remoto()}, "Usa la webcam.", tel)
    verifica("telefono senza PC collegato, «usa la webcam» con una foto: nessuna spinta",
             not righe and "foto_spinta_pc" not in regole, (righe, regole))
    righe, regole, _, _ = spinta({"portatile": remoto()}, "Cosa vedi sul mio schermo?", tel)
    verifica("telefono senza PC collegato, «cosa vedi sul mio schermo?»: nessuna spinta",
             not righe and "foto_spinta_pc" not in regole, (righe, regole))
    righe, regole, _, _ = spinta({"portatile": remoto(("schermata", "webcam"))},
                                 "Usa la webcam.", dispositivo.descrivi("satellite", True))
    verifica("dal portatile collegato con la webcam: la spinta c'è",
             len(righe) == 1 and "cosa=webcam" in righe[0] and "foto_spinta_pc" in regole,
             (righe, regole))
    righe, regole, _, _ = spinta({"portatile": remoto(("schermata", "webcam"))},
                                 "Usa la webcam.", tel)
    verifica("dal telefono col portatile collegato (pc_guarda lo raggiunge): la spinta c'è",
             len(righe) == 1 and "foto_spinta_pc" in regole, (righe, regole))
    righe, regole, _, _ = spinta({"portatile": remoto(("schermata",))}, "Usa la webcam.")
    verifica("portatile collegato senza webcam: nessuna spinta per la webcam",
             not righe and "foto_spinta_pc" not in regole, (righe, regole))
    righe, _, _, _ = spinta({"portatile": remoto(("schermata",))}, "Cosa vedi sul mio schermo?")
    verifica("portatile collegato senza webcam: la spinta per lo schermo resta",
             len(righe) == 1 and "cosa=schermo" in righe[0], righe)
    righe, regole, _, _ = spinta({"portatile": PCFinto()}, "Guarda con la webcam.")
    verifica("il PC di questo computer (esecutore locale): la spinta c'è",
             len(righe) == 1 and "foto_spinta_pc" in regole, (righe, regole))
    # Chi parla (revisione della PR #119): come i permessi di pc_guarda
    collegato = {"portatile": remoto(("schermata", "webcam"))}
    for nome, chi, prop in [
            ("un ospite", Chi(None, "ospite", None), ("Dario",)),
            ("chi non è proprietario", Chi(), ("Bianca",)),
            ("scritto da uno schermo", Chi(come="schermo"), ("Dario",)),
            ("zona grigia (dalla conversazione)", Chi(come="conversazione", sessione=True),
             ("Dario",)),
            ("frase breve", Chi(come="breve", sessione=True), ("Dario",))]:
        righe, regole, turno, _ = spinta(collegato, "Usa la webcam.",
                                         dispositivo.descrivi("telefono"), chi, prop)
        verifica(f"contrario, {nome} col portatile collegato: nessuna spinta e niente "
                 f"«collegato»", not righe and "foto_spinta_pc" not in regole
                 and "collegato a parte" not in turno and "non sono per chi parla" in turno,
                 (righe, regole, turno))
    righe, regole, turno, _ = spinta(collegato, "Usa la webcam.", dispositivo.descrivi("telefono"),
                                     Chi("Dario", "amministra"), ("Bianca",))
    verifica("chi amministra, anche non proprietario: la spinta e «collegato a parte»",
             len(righe) == 1 and "collegato a parte" in turno, (righe, turno))


def prova_dati_turno():
    _, _, turno, b = spinta({"portatile": remoto()}, "Sei un computer?",
                            dispositivo.descrivi("telefono"))
    verifica("telefono senza PC: «dispositivo: il telefono, non un computer; nessun computer»",
             "dispositivo: il telefono, non un computer; nessun computer collegato" in turno
             and "niente webcam" in turno, turno)
    "".join(b.stream_reply("E allora?", "familiare"))
    dopo = [x["content"] for x in b.backend.visti[-1] if x["role"] == "system"
            and x["content"].startswith("Dati del turno")]
    verifica("il dispositivo vale una risposta sola (il ciclo lo rimette a ogni turno)",
             dopo and "dispositivo:" not in dopo[0], dopo)
    _, _, turno, _ = spinta({"portatile": remoto(("webcam",))}, "Sei un computer?",
                            dispositivo.descrivi("telefono"))
    verifica("telefono col portatile collegato: il portatile collegato a parte",
             "dispositivo: il telefono, non un computer; il portatile è collegato a parte."
             in turno, turno)
    _, _, turno, _ = spinta({"portatile": remoto(("webcam",))}, "Sei un computer?",
                            dispositivo.descrivi("satellite", True))
    verifica("dal portatile: «dispositivo: il portatile, un computer»",
             "dispositivo: il portatile, un computer." in turno, turno)
    _, _, turno, _ = spinta({"portatile": remoto()}, "Sei un computer?",
                            dispositivo.descrivi("satellite"))
    verifica("satellite vocale senza PC: satellite vocale, nessun computer",
             "dispositivo: un satellite vocale" in turno and "nessun computer" in turno, turno)
    _, _, turno, _ = spinta({}, "Sei un computer?", dispositivo.descrivi("scritto"))
    verifica("scritto da uno schermo senza PC", "dispositivo: uno schermo, per scritto" in turno
             and "nessun computer" in turno, turno)
    _, _, turno, _ = spinta({"portatile": remoto(("webcam",))}, "Sei un computer?",
                            dispositivo.descrivi("scritto"), Chi(come="schermo"))
    verifica("scritto (anche dal browser del portatile): mai «non un computer»",
             "dispositivo: uno schermo, per scritto;" in turno
             and "non un computer" not in turno, turno)
    _, _, turno, _ = spinta({"portatile": remoto(("webcam",))}, "Sei un computer?",
                            dispositivo.descrivi("satellite", True), Chi(None, "ospite", None))
    verifica("dal portatile, un ospite: un computer, ma webcam e schermo non per lui",
             "dispositivo: il portatile, un computer; la sua webcam e il suo schermo non sono "
             "per chi parla adesso." in turno, turno)
    _, _, turno, _ = spinta({}, "Sei un computer?", dispositivo.descrivi("locale"))
    verifica("audio di questo computer senza il controllo del PC: un computer che non comandi",
             "dispositivo: un computer che non comandi" in turno, turno)
    _, _, turno, _ = spinta({"portatile": remoto()}, "Sei un computer?")
    verifica("contrario: senza dispositivo nessuna riga «dispositivo:»",
             turno and "dispositivo:" not in turno, turno)
    verifica("contrario: un canale sconosciuto non dà dispositivo",
             dispositivo.descrivi("radio") is None and dispositivo.descrivi(None) is None)
    rotto = types.SimpleNamespace(collegato=lambda: 1 / 0)
    verifica("un esecutore guasto vale «non raggiungibile»",
             dispositivo.pc_raggiungibile({"portatile": rotto}) is None)


def prova_ciclo():
    from calliope.ciclo import Ciclo

    def finto(listener, satelliti, sid=None):
        return types.SimpleNamespace(listener=listener, s=types.SimpleNamespace(satelliti=satelliti),
                                     corsia=types.SimpleNamespace(satellite_id=sid))
    t = types.SimpleNamespace(scritto={"tipo": "scritto"})
    d = Ciclo._dispositivo_turno(finto(None, None), t)
    verifica("ciclo: frase scritta → scritto", d == {"canale": "scritto", "pc_qui": False}, d)
    t = types.SimpleNamespace(scritto=None)
    d = Ciclo._dispositivo_turno(finto(types.SimpleNamespace(), None), t)
    verifica("ciclo: audio di questo computer → locale", d and d["canale"] == "locale", d)
    L = types.SimpleNamespace(remoto=True, canale="telefono")
    d = Ciclo._dispositivo_turno(finto(L, Server(Coll(None, "telefono")), sid=3), t)
    verifica("ciclo: dal telefono → telefono, non è il PC",
             d == {"canale": "telefono", "pc_qui": False}, d)
    L = types.SimpleNamespace(remoto=True, canale="satellite")
    d = Ciclo._dispositivo_turno(finto(L, Server(Coll({"capacita": ["webcam"]}))), t)
    verifica("ciclo: dal satellite con l'esecutore del PC → il PC stesso",
             d == {"canale": "satellite", "pc_qui": True}, d)

    # Il collegamento dell'ultima frase vale più dell'attivo (revisione della PR #119)
    L = types.SimpleNamespace(remoto=True, canale="satellite",
                              _ultima=(Coll(None, "telefono"), 7))
    d = Ciclo._dispositivo_turno(finto(L, Server(Coll({"capacita": ["webcam"]}))), t)
    verifica("ciclo: l'ultima frase dal telefono, l'attivo ora il portatile → telefono",
             d == {"canale": "telefono", "pc_qui": False}, d)

    class Rotto:
        def attivo_pronto(self, sat_id=None):
            raise RuntimeError("guasto")
    L = types.SimpleNamespace(remoto=True, canale="satellite")
    d = Ciclo._dispositivo_turno(finto(L, Rotto()), t)
    verifica("ciclo: un guasto del server → None (la voce non si ferma)", d is None, d)


def prova_motivo():
    """Il solo telefono: «il portatile non è collegato», non «il satellite collegato non offre
    il controllo… va aggiornato» (caso del 15/10 sera); un satellite vecchio senza esecutore
    resta com'era."""
    m = remoto().motivo_non_collegato()
    verifica("solo il telefono: «il portatile non è collegato a Calliope»",
             m == "il portatile non è collegato a Calliope", m)
    m = RemotePCExecutor(Server(Coll(None, "satellite")), "portatile").motivo_non_collegato()
    verifica("contrario: un satellite senza esecutore dice ancora di aggiornarlo",
             "non offre il controllo" in m, m)


def prova_prompt():
    from calliope.config import Config
    p = Config().prompt_for(biblioteca=False)
    verifica("prompt: i volti non si riconoscono, il nome solo se detto",
             "non riconosci i volti" in p and "altrimenti di' che non lo sai" in p)


if __name__ == "__main__":
    prova_spinta()
    prova_dati_turno()
    prova_ciclo()
    prova_motivo()
    prova_prompt()
    print(f"\n{'Tutto bene' if not ERRORI else 'Fallite: ' + ', '.join(ERRORI)}")
    sys.exit(1 if ERRORI else 0)
