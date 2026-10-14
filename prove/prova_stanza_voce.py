import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

"""La conversazione di stanza (passo 1, 13/10/2026) con i satelliti veri, in tempo reale.

Parte 1, il satellite Python vero (calliope/satellite/client.py, microfono e casse finti come
prova_satellite, frasi di Piper) col server dei satelliti nel processo e la stanza accesa:
- il satellite si collega con il protocollo 3 e il rubinetto si apre;
- una frase senza il nome, a Calliope addormentata: 0 byte sul flusso dei comandi, un segmento
  della stanza che diventa una riga;
- «Calliope, che ore sono?»: la frase arriva intera ai comandi (woke, durata come senza la
  stanza: nessun frame perso dal rubinetto) e il segmento della stanza che la copre è legato al
  turno (non si trascrive due volte);
- mentre Calliope parla (casse finte) una frase sopra la sua voce non diventa una riga
  (half-duplex: segmento buttato con «voce»); `ospiti`: il satellite smette di mandare.

Parte 2, il telefono nel browser vero (la pagina /telefono, microfono finto del browser, come
prova_telefono_pagina): con la stanza accesa e il microfono acceso una frase senza il nome
manda segmenti della stanza (righe sul server) e nessun byte dei comandi; il segno «Ascolto la
stanza» sotto lo stato; l'interruttore spento ferma i b"R"; misura della banda (kB per secondo
di parlato).

Servono le voci di Piper, i modelli della wake word, onnxruntime-web e Edge o Chromium: se
mancano le parti si saltano (77 se tutte). ~70 s.
"""

import json
import shutil
import tempfile
import threading
import time
from pathlib import Path

import numpy as np

import prova_satellite as PS

RADICE = Path(__file__).resolve().parent.parent
TMP = Path(tempfile.mkdtemp(prefix="calliope-stanza-voce-"))
errori = 0
fatte = 0
MISURE = {}


def verifica(nome, ok, dettaglio=""):
    global errori
    errori += not ok
    print(("ok  " if ok else "ERR ") + nome + (f"  ({dettaglio})" if dettaglio else ""),
          flush=True)


class STTFinto:
    def __init__(self):
        self.durate = []
        self.ultima_scartata = None

    def transcribe(self, audio, prompt=None):
        self.durate.append(len(audio) / 16000)
        return f"parlato di {len(audio) / 16000:.1f} secondi"


def stanza_per(cfg, srv):
    from calliope.corsie import STTCondiviso
    from calliope.stanza import misure
    from calliope.stanza.ascolto import Stanza
    stt = STTCondiviso(STTFinto())
    st = Stanza(cfg, stt, misure=misure.Misure(str(TMP / "registro"), 60), log=lambda m: None)
    st.server = srv
    srv.conversazione_stanza = st
    return st, stt._stt


def ascolta(lst, wake=True):
    r = {}

    def corri():
        a = lst.listen(object() if wake else None, 0.0, wakeup=r["sveglia"])
        r.update(audio=a, woke=lst.woke, fine=time.monotonic())
    r["sveglia"] = threading.Event()
    threading.Thread(target=corri, daemon=True).start()
    return r


def parte_satellite(frasi):
    global fatte
    from calliope.satellite.archivio import ArchivioSatelliti
    from calliope.satellite.client import Satellite
    from calliope.satellite.server import AscoltoRemoto, ServerSatelliti, UscitaRemota
    cfg = PS.cfg_prova(TMP, stanza="ombra", audio_modo="satellite")
    arch = ArchivioSatelliti(cfg.memory_db)
    srv = ServerSatelliti(cfg, arch, log=lambda m: None).avvia()
    srv.avviato.set()
    st, stt = stanza_per(cfg, srv)
    url = f"ws://127.0.0.1:{srv.port}"
    scena, casse = PS.Scena(), PS.Casse()
    cfg_s = PS.cfg_prova(TMP, satellite_server=url, satellite_credenziali=str(TMP / "s.json"))
    sat = Satellite(cfg_s, sorgente=lambda **kw: PS.MicFinto(scena, **kw),
                    apri_uscita=casse.flusso, log=lambda m: None)
    threading.Thread(target=sat.esegui, daemon=True).start()
    try:
        PS.aspetta(lambda: sat.codice is not None, 8)
        arch.abbina(sat.codice or "", "cucina")
        verifica("satellite vero: collegato col protocollo 3 e la stanza accesa",
                 PS.aspetta(lambda: sat.collegato.is_set(), 10) and sat.versione == 3
                 and sat.stanza is not None and sat.stanza.attiva
                 and sat.listener.rubinetto is not None)
        sid = srv.attivo.satellite["id"]
        lst = AscoltoRemoto(srv, cfg)
        # 1. senza il nome, addormentata
        r = ascolta(lst)
        coll = srv.attivo
        prima_a = coll.ricevuti
        ev = scena.di(np.concatenate([frasi["Che tempo fa domani a Milano?"],
                                      np.zeros(16000, np.float32)]))
        ev.wait(15)
        reg = st.registro(sid)
        riga = PS.aspetta(lambda: reg.righe(), 6)
        verifica("senza il nome: una riga della stanza, niente ai comandi",
                 bool(riga) and r.get("audio") is None and sat.audio_inviato == 0,
                 f"righe {len(reg.righe())}, audio comandi {sat.audio_inviato}")
        MISURE["byte_stanza_frase"] = sat.stanza.inviato
        r["sveglia"].set()
        PS.aspetta(lambda: r.get("fine"), 5)
        # 2. con il nome
        n_stt = len(stt.durate)
        r = ascolta(lst)
        x = frasi["Calliope, che ore sono?"]
        scena.di(np.concatenate([x, np.zeros(16000, np.float32)]))
        PS.aspetta(lambda: r.get("fine"), 15)
        a = r.get("audio")
        verifica("con il nome: la frase arriva intera ai comandi (nessun frame perso)",
                 a is not None and r.get("woke") and len(a) >= len(x) * 0.95,
                 f"{len(a) / 16000:.2f} s su {len(x) / 16000:.2f}" if a is not None else "")
        legato = PS.aspetta(lambda: [e for e in reg.eventi("segmento")
                                     if e.dati.get("turno") is not None], 5)
        time.sleep(0.3)
        verifica("con il nome: il segmento della stanza è legato al turno, niente doppio Whisper",
                 bool(legato) and len(stt.durate) == n_stt, f"{len(stt.durate) - n_stt} in più")
        # 3. mentre Calliope parla
        n_righe = len(reg.righe())
        uscita = UscitaRemota(srv)
        storia = (np.tile(frasi["Calliope, che ore sono?"], 4) * 32767).astype("<i2").tobytes()
        uscita.invia(1, "Una frase lunga di Calliope.", storia, 16000)
        PS.aspetta(lambda: sat.player.in_corso, 5)
        scena.di(frasi["Che tempo fa domani a Milano?"])
        PS.aspetta(lambda: not sat.player.in_corso and not sat.player.occupato(), 20)
        time.sleep(1.5)
        verifica("mentre Calliope parla: la frase sopra la sua voce non diventa una riga "
                 "(half-duplex)", len(reg.righe()) == n_righe,
                 f"buttati {sat.stanza.seg.buttati}")
        uscita.fine_turno()
        scena.di(np.concatenate([frasi["Che tempo fa domani a Milano?"],
                                 np.zeros(16000, np.float32)])).wait(15)
        verifica("a voce finita la stanza ascolta di nuovo (contrario)",
                 PS.aspetta(lambda: len(reg.righe()) > n_righe, 6))
        # 4. ospiti
        st.pausa(sid, "ospiti", 240)
        verifica("ospiti: il satellite smette di mandare la stanza",
                 PS.aspetta(lambda: not sat.stanza.attiva, 5))
        byte = sat.stanza.inviato
        scena.di(frasi["Che tempo fa domani a Milano?"]).wait(15)
        time.sleep(1.0)
        verifica("ospiti: nessun byte della stanza", sat.stanza.inviato == byte)
        fatte += 1
    finally:
        sat.ferma()
        st.chiudi()
        srv.ferma()
        arch.close()


def parte_telefono(frasi):
    global fatte
    import prova_telefono_pagina as TP
    exe = TP.browser()
    if exe is None:
        print("SALTATA IN PARTE: nessun Edge né Chromium, niente telefono")
        return
    from calliope.config import Config
    from calliope.schermi import telefono
    c = Config()
    c.telefono_web = str(TP.cartella_web())
    c.wake_model = str(TP.cartella_wake() / "calliope.onnx")
    s = telefono.stato(c)
    if not all(s["ort"].values()) or not all(s["modelli"].values()):
        print("SALTATA IN PARTE: mancano onnxruntime-web o i modelli della wake word, niente "
              "telefono")
        return
    TP.TMP = TMP
    TP.scrivi_wav(TMP / "senza_nome.wav", TP.scena(frasi["Che tempo fa domani a Milano?"]))
    amb = TP.Ambiente()
    amb.cfg.stanza = "ombra"
    st, stt = stanza_per(amb.cfg, amb.srv)
    st.schermi = amb.hub
    opz = ("--use-fake-ui-for-media-stream", "--use-fake-device-for-media-stream",
           f"--use-file-for-fake-audio-capture={TMP / 'senza_nome.wav'}")
    pagina = TP.Pagina(exe, amb.url + "/telefono/", opz, profilo="stanza")
    try:
        TP.aspetta(lambda: pagina.valuta("!!window.calliopeTelefono"), 15)
        if not TP.abbina_pagina(amb, pagina):
            verifica("telefono: abbinamento", False)
            return
        TP.aspetta(lambda: pagina.stato().get("collegato"), 15)
        TP.aspetta(lambda: pagina.stato().get("modelli") in ("pronti", "errore"), 60)
        s = pagina.stato()
        verifica("telefono: la stanza accesa dal server, interruttore acceso di serie",
                 (s.get("stanza") or {}).get("server", {}).get("attiva") is True
                 and s["stanza"]["voluta"] is True, str(s.get("stanza")))
        r = TP.ascolta_in_thread(amb, wake=True, awake_until=0.0)
        pagina.valuta("window.calliopeTelefono.impostaMic(true).then(() => 1)")
        TP.aspetta(lambda: pagina.stato().get("mic"), 10)
        coll = amb.srv.attivo_pronto()
        sid = coll.satellite["id"] if coll is not None else None
        t0 = time.monotonic()
        righe = TP.aspetta(lambda: sid is not None and len(st.registro(sid).righe()) >= 2, 25)
        s = pagina.stato()
        verifica("telefono: frasi senza il nome → righe della stanza, 0 byte ai comandi",
                 bool(righe) and s.get("inviato") == 0 and r.get("audio") is None,
                 f"righe {len(st.registro(sid).righe()) if sid else '?'}, comandi "
                 f"{s.get('inviato')}, stanza {s['stanza']['inviato']} byte")
        verifica("telefono: il segno «Ascolto la stanza» sotto lo stato",
                 s["stanza"]["segno"] == "Ascolto la stanza" and "Ascolto la stanza" in (
                     pagina.valuta("document.getElementById('tel-dove').textContent") or ""))
        parlato = sum(e.dati.get("voce_s") or 0 for e in st.registro(sid).eventi("segmento"))
        if parlato:
            MISURE["telefono_kB_per_s_parlato"] = round(s["stanza"]["inviato"] / 1024 / parlato,
                                                        1)
            MISURE["telefono_MB_per_ora_parlato"] = round(
                s["stanza"]["inviato"] / 2 ** 20 / parlato * 3600, 1)
        MISURE["telefono_s"] = round(time.monotonic() - t0, 1)
        pagina.valuta("window.calliopeTelefono.impostaStanza(false); 1")
        time.sleep(1.0)
        b = pagina.stato()["stanza"]["inviato"]
        time.sleep(6)
        s = pagina.stato()
        verifica("telefono: interruttore spento → nessun b\"R\", il segno lo dice",
                 s["stanza"]["inviato"] == b and s["stanza"]["attiva"] is False
                 and "spento" in s["stanza"]["segno"], str(s["stanza"]))
        pagina.valuta("window.calliopeTelefono.impostaStanza(true); 1")
        r["sveglia"].set()
        pagina.valuta("window.calliopeTelefono.impostaMic(false).then(() => 1)")
        fatte += 1
    finally:
        errori_js = [x for x in pagina.log if x.startswith(("ECCEZIONE", "ERROR"))]
        verifica("telefono: nessun errore JavaScript", not errori_js, "; ".join(errori_js)[:300])
        pagina.chiudi()
        st.chiudi()
        amb.chiudi()


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass
    # Pronunce senza il rumore di Piper: la prova non ripete la frase se la wake word non
    # scatta, e con il rumore «Calliope, che ore sono?» non la svegliava ~1 volta su 10 (14/10)
    frasi = PS.sintetizza(["Che tempo fa domani a Milano?", "Calliope, che ore sono?"],
                          deterministica=True)
    if frasi is None or not (RADICE / "wakeword" / "modelli" / "calliope.onnx").is_file():
        print("Voci di Piper o modelli della wake word assenti: prova saltata.")
        return 77
    try:
        parte_satellite(frasi)
        parte_telefono(frasi)
    finally:
        shutil.rmtree(TMP, ignore_errors=True)
    print("\nMisure: " + json.dumps(MISURE, ensure_ascii=False))
    if not fatte:
        return 77
    print("\nTutto bene." if not errori else f"\n{errori} prove non riuscite.")
    return 1 if errori else 0


if __name__ == "__main__":
    sys.exit(main())
