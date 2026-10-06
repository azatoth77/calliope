"""
La fase del telefono della prova end-to-end (06/10/2026), sul portatile: sulla DGX non c'è un
browser (installarlo vuole sudo). La pagina vera del telefono dell'istanza di prova si apre in
Edge senza finestra attraverso un tunnel SSH verso la porta degli schermi dell'istanza
(http://127.0.0.1 è un contesto sicuro: microfono e service worker funzionano), con il
microfono finto di Edge (`--use-file-for-fake-audio-capture`: «Calliope, che ore sono?» con una
voce di Piper, ripetuta). La pagina si abbina (il codice va sulla DGX in
`~/calliope-e2e/telefono.codice`, il runner lo abbina come telefono personale di Andrea),
prepara VAD e wake word nel browser, accende il microfono e manda la frase; l'esito (byte
mandati e ricevuti, errori della pagina) torna in `~/calliope-e2e/telefono.fatto`.

Lo lancia `lancia.py --telefono` quando il runner scrive «TELEFONO PRONTO porta N».
"""
from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

QUI = Path(__file__).resolve().parent
RADICE = QUI.parent.parent
sys.path.insert(0, str(RADICE / "prove"))
sys.path.insert(0, str(RADICE))

from prove.e2e.lancia import ALIAS, DATI, SSH, registrazioni, ssh  # noqa: E402


def _voci() -> Path:
    v = RADICE / "voices"
    return v if any(v.glob("*.onnx")) else registrazioni().parent / "voices"


def prova(porta_remota: int) -> dict:
    import numpy as np
    import prova_telefono_pagina as T
    from prove.e2e.voci import ricampiona
    esito: dict = {"errori": []}
    exe = T.browser()
    if exe is None:
        return {"errori": ["né Edge né Chromium sul portatile"]}
    from piper import PiperVoice
    v = PiperVoice.load(str(_voci() / "it_IT-ugo-medium.onnx"))
    pcm = b"".join(c.audio_int16_bytes for c in v.synthesize("Calliope, che ore sono?"))
    x = ricampiona(np.frombuffer(pcm, np.int16).astype(np.float32) / 32768,
                   v.config.sample_rate)
    wav = T.TMP / "che_ore.wav"
    T.scrivi_wav(wav, T.scena(x, ripeti=6))
    locale = T.porta_libera()
    tunnel = subprocess.Popen([SSH, "-o", "BatchMode=yes", "-o", "ExitOnForwardFailure=yes",
                               "-N", "-L", f"127.0.0.1:{locale}:127.0.0.1:{porta_remota}", ALIAS],
                              stdin=subprocess.DEVNULL)
    pagina = None
    try:
        import socket
        for _ in range(50):
            try:
                socket.create_connection(("127.0.0.1", locale), 1).close()
                break
            except OSError:
                time.sleep(0.2)
        url = f"http://127.0.0.1:{locale}/telefono/"
        # --mute-audio (07/10): la voce di Calliope non deve uscire dalle casse vere del
        # portatile; la prova conta i byte ricevuti dalla pagina, non ciò che si sente
        opz = ("--use-fake-ui-for-media-stream", "--use-fake-device-for-media-stream",
               f"--use-file-for-fake-audio-capture={wav}", "--mute-audio")
        pagina = T.Pagina(exe, url, opz, profilo="e2e")
        if not T.aspetta(lambda: pagina.valuta("!!window.calliopeTelefono"), 30):
            esito["errori"].append("pagina del telefono non caricata")
            return esito
        pagina.valuta("document.getElementById('tel-nome').value='Andrea';"
                      "document.getElementById('tel-chiedi').click(); 1")
        cod = T.aspetta(lambda: (pagina.valuta("document.getElementById('tel-codice-cifre')"
                                               ".textContent") or "").replace(" ", ""), 20)
        if not cod or len(cod) != 6:
            esito["errori"].append(f"nessun codice d'abbinamento ({cod!r})")
            return esito
        ssh(f"echo {int(cod):06d} > ~/{DATI}/telefono.codice")
        if not T.aspetta(lambda: pagina.stato().get("collegato"), 40):
            esito["errori"].append("la pagina non si collega dopo l'abbinamento")
            return esito
        t0 = time.monotonic()
        T.aspetta(lambda: pagina.stato().get("modelli") in ("pronti", "errore"), 90)
        s = pagina.stato()
        esito["modelli"] = s.get("modelli")
        esito["preparazione_s"] = round(time.monotonic() - t0, 1)
        if s.get("modelli") != "pronti":
            esito["errori"].append(f"modelli non pronti: {s.get('erroreModelli')}")
            return esito
        pagina.valuta("window.calliopeTelefono.impostaMic(true).then(() => 1)")
        if not T.aspetta(lambda: pagina.stato().get("mic"), 15):
            esito["errori"].append("microfono finto non acceso")
            return esito
        # Il saluto è già arrivato: conta la voce ricevuta dopo la frase mandata
        time.sleep(4)
        base = pagina.stato().get("ricevuti") or 0
        mandata = T.aspetta(lambda: (pagina.stato().get("inviato") or 0) > 0, 60)
        ok = bool(mandata) and T.aspetta(
            lambda: (pagina.stato().get("ricevuti") or 0) > base + 20000, 60)
        s = pagina.stato()
        esito["ricevuti_prima"] = base
        esito.update(inviato=s.get("inviato"), ricevuti=s.get("ricevuti"),
                     attivo=s.get("attivo"))
        if not ok:
            esito["errori"].append(f"nessuno scambio di voce (inviati {s.get('inviato')}, "
                                   f"ricevuti {s.get('ricevuti')})")
        time.sleep(3)
        pagina.valuta("window.calliopeTelefono.impostaMic(false).then(() => 1)")
        pagina.pompa(0.5)
        esito["log_pagina"] = [r[:200] for r in pagina.log[:15]]
        return esito
    except Exception as e:  # noqa: BLE001
        esito["errori"].append(f"{type(e).__name__}: {e}")
        return esito
    finally:
        if pagina is not None:
            pagina.chiudi()
        tunnel.terminate()
        try:
            tunnel.wait(5)
        except subprocess.TimeoutExpired:
            tunnel.kill()


def main(porta: int) -> int:
    esito = prova(porta)
    dati = json.dumps(esito, ensure_ascii=False)
    subprocess.run([SSH, "-o", "BatchMode=yes", ALIAS,
                    f"cat > ~/{DATI}/telefono.fatto"], input=dati.encode("utf-8"))
    print("Telefono:", dati)
    return 0 if not esito.get("errori") else 1


if __name__ == "__main__":
    sys.exit(main(int(sys.argv[1])))
