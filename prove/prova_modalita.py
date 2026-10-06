import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

"""Prova a secco della modalità cambiata a voce (05/10, calliope/modalita.py).

Caso vero della DGX (05/10 21:10): «la proviamo la modalità Star Trek» cambiava solo il tono
(«Modalità computer di bordo attiva.»), e a «non sento i suoni» il modello inventava una
«limitazione hardware». Qui:
- configurazione: andata e ritorno senza riavvio, le chiavi di calliope.locale.yaml restano,
  nomi detti e contrari, i due classificatori («Computer» e «Calliope»), frase del prompt solo
  con la modalità (senza, il prompt è quello di prima parola per parola);
- tool: cambia_voce(modalita=…) solo a chi amministra riconosciuto dalla voce (familiare,
  ospite, frase breve con la sfida, scritto), il tono resta un tono, la risposta dice cosa è
  acceso (wake word testuale se manca il modello, satelliti da riavviare), ritorno alla
  normale con il tono di prima, gli ascoltatori di main avvisati;
- persistenza in personalita.json (vale il più recente);
- satelliti con il server vero e un satellite vero (microfono finto): aggiornamento senza
  riconnessione, modello mancante mandato dal server con SHA-256 e dimensione, file chiesti
  fuori dall'elenco rifiutati, impronta sbagliata rifiutata, satellite vecchio da riavviare,
  ritorno alla normale.
"""

import json
import tempfile
import threading
import time
import types
from pathlib import Path

from calliope import config as C
from calliope.config import Config, cambia_modalita, nome_modalita

errori = 0


def verifica(nome, ottenuto, atteso):
    global errori
    ok = ottenuto == atteso
    errori += not ok
    print(f"{'ok ' if ok else 'ERR'} {nome} → {ottenuto!r}" + ("" if ok else f"  (atteso {atteso!r})"))


def aspetta(cond, timeout=8.0) -> bool:
    fine = time.monotonic() + timeout
    while time.monotonic() < fine:
        if cond():
            return True
        time.sleep(0.02)
    return bool(cond())


TMP = Path(tempfile.mkdtemp(prefix="calliope-modalita-"))

# ── configurazione ──
for detto, atteso in [("Star Trek", "startrek"), ("startrek", "startrek"), ("star-trek", "startrek"),
                      ("modalità Star Trek", "startrek"), ("normale", "normale"), (None, "normale"),
                      ("nessuna", "normale"), ("", "normale"),
                      # contrari
                      ("pizza", None), ("formale", None), ("Paola", None)]:
    verifica(f"nome_modalita «{detto}»", nome_modalita(detto), atteso)

c = Config()
p_normale = c.prompt_for(False)
c._impostate_locale = {"tono"}            # il tono scritto in calliope.locale.yaml
c.tono = "ironico"
cambia_modalita(c, "Star Trek")
verifica("startrek a caldo", (c.modalita, c.wake_names, c.wake_start_only, c.suoni_ascolto,
                              Path(c.wake_model).name), ("startrek", ["Computer", "Calliope"], True,
                                                         True, "computer.onnx"))
verifica("startrek: il tono del file locale resta", c.tono, "ironico")
verifica("prompt: la modalità in fondo, con le parole e i suoni",
         all(x in c.prompt_for(False) for x in ("modalità Star Trek", "suona un breve segnale",
                                                "chiama i tool come sempre")), True)
verifica("contrario prompt: niente parola che sveglia (il 4B la ripeteva in testa)",
         "Computer" in c.prompt_for(False)[len(p_normale) - 200:], False)
cambia_modalita(c, "normale")
verifica("ritorno alla normale", (c.modalita, c.wake_names, c.suoni_ascolto, c.wake_posizione,
                                  Path(c.wake_model).name, c.wake_match),
         (None, ["Calliope"], False, "ovunque", "calliope.onnx", 0.78))
c.tono = "normale"
verifica("contrario prompt: senza modalità è quello di prima", c.prompt_for(False) == p_normale, True)
try:
    cambia_modalita(c, "pizza")
    verifica("modalità sconosciuta: errore", False, True)
except ValueError:
    verifica("modalità sconosciuta: errore, niente cambia", (c.modalita, c.wake_names), (None, ["Calliope"]))

# I due classificatori: «Computer» e, se il file c'è, «Calliope» accanto
mod_dir = TMP / "modelli"
mod_dir.mkdir()
(mod_dir / "calliope.onnx").write_bytes(b"calliope" * 1000)
c2 = Config()
c2.wake_model = str(mod_dir / "calliope.onnx")
cambia_modalita(c2, "startrek")
c2.wake_model = str(mod_dir / "computer.onnx")
verifica("wake_models con calliope.onnx accanto", [Path(m).name for m in c2.wake_models],
         ["computer.onnx", "calliope.onnx"])
c2.wake_anche_nome = False
verifica("contrario: senza wake_anche_nome solo computer", [Path(m).name for m in c2.wake_models],
         ["computer.onnx"])
c2.wake_anche_nome = True
verifica("contrario: senza modalità un classificatore solo", len(Config().wake_models), 1)

# ── tool: cambia_voce(modalita=…) ──
from calliope.modalita import Modalita  # noqa: E402
from calliope.speaker_id import UserProfile  # noqa: E402
from calliope.tools.builtin import _cambia_voce  # noqa: E402


class Registro:
    def __init__(self):
        self.p = {"Dario": UserProfile("Dario", admin=True), "Bianca": UserProfile("Bianca")}

    def get(self, n):
        return self.p.get(n)

    def save(self):
        pass


REG = Registro()
cfg = Config()
cfg.config_dir = str(TMP)
(TMP / "calliope.yaml").write_text("", encoding="utf-8")
os.utime(TMP / "calliope.yaml", (time.time() - 100, time.time() - 100))
MOD = Modalita(cfg, log=lambda *a: None)
avvisi = []
MOD.ascoltatori.append(lambda cf: avvisi.append(cf.modalita) or {"satelliti_da_riavviare": ["cucina"]})


def contesto(chi, livello, come="voce", profilo=None):
    sc = types.SimpleNamespace(current_speaker=chi, current_level=livello, identified_by=come,
                               profile_level=profilo or livello, sfida=None, sfida_superata=False,
                               conferma_breve=False)
    return types.SimpleNamespace(cfg=cfg, speakers=REG, speaker=None, regole=[], speaker_ctx=sc,
                                 modalita=MOD, turno=1, tool_in_sospeso=None, user_text="")


r = _cambia_voce(contesto("Bianca", "familiare"), modalita="startrek")
verifica("familiare: rifiutato, niente cambia", (r["ok"], cfg.modalita, avvisi,
                                                 (TMP / "personalita.json").exists()),
         (False, None, [], False))
r = _cambia_voce(contesto(None, "ospite"), modalita="startrek")
verifica("ospite: rifiutato", (r["ok"], cfg.modalita), (False, None))
r = _cambia_voce(contesto("Dario", "familiare", "breve"), modalita="startrek")
verifica("chi amministra con una frase breve: la frase di sfida",
         (r["ok"], cfg.modalita, "ripeti" in r.get("risposta_finale", "")), (False, None, True))
r = _cambia_voce(contesto("Dario", "familiare", "schermo", "amministra"), modalita="startrek")
verifica("scritto: me lo chiedi a voce", (r["ok"], cfg.modalita, "in_sospeso" in r), (False, None, True))
cfg.tono = "essenziale"                   # il tono della casa di prima
# il percorso del modello della modalità è relativo: dalla cartella della prova manca
# computer.onnx anche dove il repository ce l'ha (il portatile su cui è stato addestrato)
_cwd = os.getcwd()
os.chdir(TMP)
r = _cambia_voce(contesto("Dario", "amministra"), modalita="startrek")
os.chdir(_cwd)
verifica("chi amministra dalla voce: modalità accesa subito",
         (r["ok"], cfg.modalita, cfg.wake_names[0], cfg.tono, cfg.suoni_ascolto, avvisi),
         (True, "startrek", "Computer", "computer_di_bordo", True, ["startrek"]))
frase = r["risposta_finale"]
print("    «" + frase + "»")
verifica("la risposta dice parola, suoni e cosa manca",
         all(x in frase for x in ("«Computer»", "«Calliope»", "suoni di inizio e fine ascolto",
                                  "solo dalla trascrizione", "«cucina»", "riavvio")), True)
verifica("la risposta non dice limitazioni inventate", "hardware" in frase.lower(), False)
d = json.loads((TMP / "personalita.json").read_text(encoding="utf-8"))
verifica("personalita.json: modalità, tono, tono di prima", (d["modalita"], d["tono"],
                                                             d["tono_fuori_modalita"], d["da"]),
         ("startrek", "computer_di_bordo", "essenziale", "Dario"))
r = _cambia_voce(contesto("Dario", "amministra"), modalita="startrek")
verifica("di nuovo startrek: già attiva, niente avvisi", (r["ok"], r.get("gia"), avvisi),
         (True, True, ["startrek"]))
r = _cambia_voce(contesto("Bianca", "familiare"), tono="formale")
verifica("contrario: un tono resta un tono (Bianca, solo per lei)",
         (r["ok"], REG.p["Bianca"].preferred_tone, cfg.modalita), (True, "formale", "startrek"))

# Riavvio: la modalità detta a voce torna (personalita.json più recente dei file)
from calliope.personalita import carica_tono_casa  # noqa: E402
r2 = Config()
r2.config_dir = str(TMP)
carica_tono_casa(r2, log=lambda *a: None)
verifica("riavvio: modalità e tono da personalita.json", (r2.modalita, r2.wake_names[0], r2.tono),
         ("startrek", "Computer", "computer_di_bordo"))
os.utime(TMP / "calliope.yaml", (time.time() + 5, time.time() + 5))
r3 = Config()
r3.config_dir = str(TMP)
carica_tono_casa(r3, log=lambda *a: None)
verifica("contrario: calliope.yaml più recente vince", (r3.modalita, r3.wake_names), (None, ["Calliope"]))
os.utime(TMP / "calliope.yaml", (time.time() - 100, time.time() - 100))

# Tornare alla normale SCRITTO (06/10, DGX: in startrek «Computer» non svegliava e lo scritto
# era rifiutato): ammesso dallo schermo personale di chi amministra, solo il ritorno
r = _cambia_voce(contesto("Bianca", "familiare", "schermo"), modalita="normale")
verifica("contrario: «torna alla normale» scritto da una familiare: rifiutato",
         (r["ok"], cfg.modalita), (False, "startrek"))
c_scr = contesto("Dario", "familiare", "schermo", "amministra")
r = _cambia_voce(c_scr, modalita="normale")
verifica("«torna alla normale» scritto da chi amministra: fatto, col tono di prima",
         (r["ok"], cfg.modalita, cfg.wake_names, cfg.tono, cfg.suoni_ascolto,
          "modalita_normale_scritta" in c_scr.regole, "in_sospeso" in r),
         (True, None, ["Calliope"], "essenziale", False, True, False))
r = _cambia_voce(contesto("Dario", "familiare", "schermo", "amministra"), modalita="startrek")
verifica("contrario: attivare startrek scritto chiede ancora la voce",
         (r["ok"], cfg.modalita, "in_sospeso" in r), (False, None, True))
os.chdir(TMP)
r = _cambia_voce(contesto("Dario", "amministra"), modalita="startrek")
os.chdir(_cwd)
verifica("di nuovo startrek dalla voce (per il ritorno qui sotto)", (r["ok"], cfg.modalita),
         (True, "startrek"))

r = _cambia_voce(contesto("Dario", "amministra"), modalita="normale")
verifica("ritorno alla normale: il tono della casa di prima",
         (r["ok"], cfg.modalita, cfg.wake_names, cfg.tono, cfg.suoni_ascolto, avvisi[-1]),
         (True, None, ["Calliope"], "essenziale", False, None))
verifica("frase del ritorno", r["risposta_finale"].startswith("Modalità normale"), True)
verifica("personalita.json: normale", json.loads((TMP / "personalita.json").read_text(
    encoding="utf-8"))["modalita"], "normale")
r = _cambia_voce(contesto("Dario", "amministra"), modalita="pizza")
verifica("modalità sconosciuta", (r["ok"], cfg.modalita), (False, None))


# ── satelliti: server vero, satellite vero con il microfono finto ──
def satelliti():
    from websockets.sync.client import connect
    from calliope.satellite import protocollo as P
    from calliope.satellite.archivio import ArchivioSatelliti
    from calliope.satellite.client import Satellite
    from calliope.satellite.server import ServerSatelliti
    from calliope.suoni import SuoniAscolto
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import prova_satellite as T

    srv_dir, sat_dir = TMP / "server", TMP / "satellite"
    (srv_dir / "modelli").mkdir(parents=True)
    (sat_dir / "modelli").mkdir(parents=True)
    computer = os.urandom(50_000)
    (srv_dir / "modelli" / "calliope.onnx").write_bytes(b"c" * 1000)
    (srv_dir / "modelli" / "computer.onnx").write_bytes(computer)
    (srv_dir / "modelli" / "melspectrogram.onnx").write_bytes(b"m")
    (sat_dir / "modelli" / "calliope.onnx").write_bytes(b"c" * 1000)
    cfg = T.cfg_prova(srv_dir)
    cfg.wake_model = str(srv_dir / "modelli" / "calliope.onnx")
    arch = ArchivioSatelliti(cfg.memory_db)
    srv = ServerSatelliti(cfg, arch, log=lambda m: None).avvia()
    srv.avviato.set()
    url = f"ws://127.0.0.1:{srv.port}"
    _, tok = arch.crea_con_token("studio")
    _, tok_vecchio = arch.crea_con_token("cucina")
    cfg_s = T.cfg_prova(sat_dir, satellite_server=url)
    cfg_s.wake_model = str(sat_dir / "modelli" / "calliope.onnx")
    Path(cfg_s.satellite_credenziali).write_text(json.dumps({"token": tok}), encoding="utf-8")

    class Finto:                                 # rilevatore finto: niente onnxruntime
        def __init__(self, p, altri=()):
            self.nomi = [Path(p).name, *[Path(a).name for a in altri]]

        def process(self, x):
            return 0.0

        def reset(self):
            pass

    log = []
    sat = Satellite(cfg_s, sorgente=lambda **kw: T.MicFinto(T.Scena(), **kw),
                    apri_uscita=T.Casse().flusso, log=log.append, rilevatore=Finto("x"))
    sat._crea_rilevatore = Finto
    threading.Thread(target=sat.esegui, daemon=True).start()
    try:
        verifica("satellite collegato, modello di sempre, nessun suono",
                 (aspetta(lambda: sat.collegato.is_set()), sat._wake_file, sat.suoni), (True, "calliope.onnx", {}))
        # Un satellite vecchio: niente «modalita» nel ciao
        vecchio = connect(url + P.PERCORSO_AUDIO, compression=None, legacy=True)
        vecchio.send(P.testo(tipo="ciao", versione=P.VERSIONE, token=tok_vecchio, primo=False))
        ben = P.leggi(vecchio.recv(timeout=3))
        vecchio.send(P.testo(tipo="pronto", eco=None))
        verifica("benvenuto con l'elenco dei modelli e le impronte",
                 [(m["nome"], m["byte"]) for m in ben.get("wake_modelli", [])], [("calliope.onnx", 1000)])
        aspetta(lambda: len([x for x in srv.collegati if x.pronto]) == 2, 3)

        # Modalità startrek a voce sul server
        cambia_modalita(cfg, "startrek")
        cfg.wake_model = str(srv_dir / "modelli" / "computer.onnx")
        srv.suoni = SuoniAscolto(cfg)
        note = srv.annuncia_modalita()
        verifica("annuncio: uno aggiornato, il vecchio da riavviare, al nuovo manca il modello",
                 (note["satelliti_aggiornati"], note["satelliti_da_riavviare"], note["satelliti_senza_modello"]),
                 (1, ["cucina"], ["studio"]))
        arrivato = aspetta(lambda: sat._wake_file == "computer.onnx", 8)
        verifica("il satellite chiede il modello, lo riceve e passa a «Computer» e «Calliope»",
                 (arrivato, sat._wake_in_uso, getattr(sat.wake, "nomi", None)),
                 (True, ["computer.onnx", "calliope.onnx"], ["computer.onnx", "calliope.onnx"]))
        verifica("file uguale a quello del server", (sat_dir / "modelli" / "computer.onnx").read_bytes() == computer,
                 True)
        verifica("parole e suoni senza riconnessione",
                 (sat.cfg.wake_word, sorted(sat.suoni), sat.connessioni), ("Computer", ["fine", "inizio"], 1))
        tipi = []
        try:
            while True:
                x = vecchio.recv(timeout=0.5)
                tipi.append(P.leggi(x).get("tipo") if isinstance(x, str) else "binario")
        except TimeoutError:
            pass
        verifica("contrario: al satellite vecchio niente «modalita»", "modalita" in tipi, False)

        # Richieste fuori dall'elenco: rifiutate
        for nome in ("melspectrogram.onnx", "../calliope.onnx", "segreto.onnx"):
            vecchio.send(P.testo(tipo="wake_richiesta", nome=nome))
            try:
                r = P.leggi(vecchio.recv(timeout=3))
            except TimeoutError:
                r = {}
            verifica(f"richiesta di «{nome}»: rifiutata", (r.get("tipo"), bool(r.get("errore"))),
                     ("wake_file", True))
        vecchio.send(P.testo(tipo="wake_richiesta", nome="computer.onnx"))
        testa = P.leggi(vecchio.recv(timeout=3))
        corpo = vecchio.recv(timeout=3)
        t, _, dati = P.apri_binario(corpo)
        verifica("richiesta del modello in uso: intestazione e file", (testa.get("byte"), t, dati == computer),
                 (len(computer), P.MODELLO, True))

        # Un file con un'impronta diversa da quella annunciata non si salva
        (sat_dir / "modelli" / "altro.onnx").unlink(missing_ok=True)
        sat._wake_annunciati["altro.onnx"] = {"sha256": "0" * 64, "byte": 3}
        sat._wake_in_arrivo = {"nome": "altro.onnx", "sha256": "0" * 64, "byte": 3}
        sat._ricevi_modello(b"abc")
        verifica("contrario: impronta sbagliata, file non salvato",
                 (sat_dir / "modelli" / "altro.onnx").exists(), False)
        sat._wake_in_arrivo = {"nome": "../fuori.onnx", "sha256": "x", "byte": 3}
        sat._ricevi_modello(b"abc")
        verifica("contrario: nome con un percorso", (TMP / "satellite" / "fuori.onnx").exists(), False)

        # Ritorno alla normale
        cambia_modalita(cfg, "normale")
        srv.suoni = None
        note = srv.annuncia_modalita()
        verifica("ritorno alla normale sul satellite",
                 (aspetta(lambda: sat._wake_file == "calliope.onnx"), sat._wake_in_uso, sat.suoni,
                  sat.cfg.wake_word, note["satelliti_senza_modello"]),
                 (True, ["calliope.onnx"], {}, None, []))
        vecchio.close()
    finally:
        sat.ferma()
        srv.ferma()
        arch.close()


satelliti()

# ── telefono: il classificatore del nome accanto ──
from calliope.schermi.telefono import file_modelli  # noqa: E402
tf = Config()
tf.wake_model = str(mod_dir / "calliope.onnx")
cambia_modalita(tf, "startrek")
tf.wake_model = str(mod_dir / "computer.onnx")
(mod_dir / "computer.onnx").write_bytes(b"x")
fm = file_modelli(tf)
verifica("telefono: computer e calliope", (Path(fm["calliope"]).name, Path(fm["nome"]).name),
         ("computer.onnx", "calliope.onnx"))
(mod_dir / "computer.onnx").unlink()
verifica("contrario telefono: senza computer.onnx solo calliope", ("nome" in file_modelli(tf),
                                                                  Path(file_modelli(tf)["calliope"]).name),
         (False, "calliope.onnx"))

# ── cambia_voce(voce=…): solo voci installate, «scarica» non è un cambio (e2e del 06/10) ──
class _Voce:
    def __init__(self):
        self.cambi = []

    def change_voice(self, path):
        self.cambi.append(path)
        return True


_cwd = os.getcwd()
_vdir = Path(tempfile.mkdtemp(prefix="voci-"))
(_vdir / "voices").mkdir()
for _f in ("it_IT-ugo-medium.onnx", "it_IT-ugo-medium.onnx.json"):
    (_vdir / "voices" / _f).write_bytes(b"x")
os.chdir(_vdir)
try:
    def voce(chi, livello, testo, nome):
        c = contesto(chi, livello)
        c.user_text, c.speaker = testo, _Voce()
        return _cambia_voce(c, voce=nome), c
    r, c = voce("Bianca", "familiare", "Calliope scarica la voce di Ugo.", "Ugo")
    verifica("«scarica la voce di Ugo» da una familiare: niente cambio, solo chi amministra "
             "scarica, la domanda se usarla", (r["ok"], c.speaker.cambi, r["risposta_finale"],
                                               r["in_sospeso"]["tool"], c.regole),
             (False, [], "Scaricare voci nuove lo può fare solo chi amministra. La voce di "
              "Ugo però c'è già: vuoi che la usi?", "cambia_voce", ["voce_scarica_non_cambia"]))
    r, c = voce("Dario", "amministra", "installa la voce di Ugo", "ugo")
    verifica("«installa la voce di Ugo» da chi amministra: la domanda, senza il rifiuto",
             (r["ok"], c.speaker.cambi, r["risposta_finale"]),
             (False, [], "La voce di Ugo però c'è già: vuoi che la usi?"))
    r, c = voce("Bianca", "familiare", "Scarica la voce di Serena.", "serena")
    verifica("«scarica» una voce non installata: niente cambio, lo dice",
             (r["ok"], c.speaker.cambi, "in_sospeso" in r, "non è installata"
              in r["risposta_finale"]), (False, [], False, True))
    r, c = voce("Bianca", "familiare", "Torna alla voce di Serena.", "Serena")
    verifica("voce non installata: mai un cambio finto", (r["ok"], c.speaker.cambi,
                                                         r["risposta_finale"]),
             (False, [], "La voce di Serena non è installata, quindi non posso usarla. Per "
              "scaricarla chiedi a chi amministra."))
    # Contrari: cambiare con una voce installata, anche se la frase dice «scaricata»
    r, c = voce("Bianca", "familiare", "Usa la voce di Ugo.", "Ugo")
    verifica("contrario: «usa la voce di Ugo» cambia, con la frase pronta",
             (r["ok"], len(c.speaker.cambi), r["risposta_finale"], c.regole),
             (True, 1, "Va bene, da adesso parlo con la voce di Ugo.", []))
    r, c = voce("Bianca", "familiare", "Metti la voce che hai scaricato ieri, Ugo.", "ugo")
    verifica("contrario: «metti la voce scaricata ieri» cambia", (r["ok"], len(c.speaker.cambi)),
             (True, 1))
finally:
    os.chdir(_cwd)

# ── elenca_voci con «scarica la voce di…» (e2e del 06/10, giro 5): non è la richiesta ──
from calliope.tools.builtin import _elenca_voci  # noqa: E402


def elenco(chi, livello, testo):
    c = contesto(chi, livello)
    c.user_text = testo
    return _elenca_voci(c), c


r, c = elenco("Giulia", "familiare", "Calliope scarica la voce di Leonardo dal catalogo.")
verifica("«scarica la voce di Leonardo» da una familiare con elenca_voci: la frase sul permesso",
         (r.get("ok"), r.get("risposta_finale"), c.regole),
         (False, "Scaricare voci nuove lo può fare solo chi amministra: chiediglielo.",
          ["voce_scarica_elenco"]))
r, c = elenco("Dario", "amministra", "Installa la voce di Leonardo.")
verifica("da chi amministra: l'elenco con l'indicazione di installa_proponi, niente frase pronta",
         ("risposta_finale" in r, "installa_proponi" in r.get("cosa_fare", ""), bool(r["voci"])),
         (False, True, True))
for testo in ("Che voci hai?", "Usa la voce di Leonardo, quella scaricata ieri."):
    r, c = elenco("Giulia", "familiare", testo)
    verifica(f"contrario: «{testo}» è l'elenco di sempre", (sorted(r), c.regole),
             (["voci"], []))

print(f"\n{'Tutto ok' if not errori else f'{errori} errori'}")
sys.exit(1 if errori else 0)
