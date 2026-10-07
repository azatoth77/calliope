"""
Calliope vera con due satelliti che parlano insieme e a turno (06/10/2026, calliope/corsie.py;
rapporto docs/ricerche/2026-10-06-conversazione-persona.md).

    python prove/prova_corsie_satelliti.py

`python -m calliope` in un sottoprocesso con `audio_modo: satellite`, Ollama e Whisper finti
(il «Whisper» riconosce la frase dalla lunghezza dell'audio, il «modello» risponde guardando
la storia: «come si chiama il mio gatto?» → il nome detto prima nella stessa conversazione),
CAM++ vero sulle voci di Piper (Dario = riccardo, Bianca = paola, l'ospite = giorgio) e due
satelliti finti a livello di protocollo (prove/satellite_finto.py), lo studio e la cucina.

  - Dario comincia nello studio e continua in cucina: la sua conversazione lo segue;
  - Bianca in cucina e un ospite nello studio non la vedono;
  - Dario e Bianca parlano insieme: con conversazioni_parallele 2 rispondono insieme, con 1 la
    seconda sente «Sto rispondendo anche a un'altra persona: dammi un attimo.» e poi la sua
    risposta;
  - la stessa frase sentita dai due satelliti (stessa stanza): risponde solo uno;
  - il registro dei turni ha il satellite e la conversazione di ogni turno.

Senza le voci di Piper, il modello di CAM++ o websockets si salta.
"""
import io
import json
import os
import re
import subprocess
import sys
import tempfile
import threading
import time
import wave
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import numpy as np

RADICE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RADICE))
sys.path.insert(0, str(RADICE / "prove"))

errori = 0
VOCI = {"Dario": "it_IT-riccardo-x_low.onnx", "Bianca": "it_IT-paola-medium.onnx",
        "ospite": "it_IT-giorgio-medium.onnx"}
CALLIOPE_VOCE = "it_IT-serena-high.onnx"
REGISTRA = ["Raccontami cosa hai fatto oggi, con calma e senza fretta.",
            "Dimmi qual è il tuo piatto preferito e perché ti piace tanto.",
            "Descrivimi la stanza in cui ti trovi adesso, con tutti i mobili."]
GATTO = "Calliope, il mio gatto si chiama Micio."
DOMANDA = "Calliope, come si chiama il mio gatto?"
STORIA = "Calliope, raccontami una storia."
TEMPO = "Calliope, che tempo fa domani?"
ORE = "Calliope, che ore sono?"


def ok(nome, cond, extra=""):
    global errori
    if not cond:
        errori += 1
    print(("ok  " if cond else "ERR ") + nome + (f"  ({extra})" if extra else ""), flush=True)


def porta_libera() -> int:
    import socket
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def sintetizza(voce: str, testo: str) -> np.ndarray:
    from piper import PiperVoice
    v = _VOCI_PIPER.get(voce)
    if v is None:
        v = _VOCI_PIPER[voce] = PiperVoice.load(str(RADICE / "voices" / voce))
    pcm = b"".join(ch.audio_int16_bytes for ch in v.synthesize(testo))
    x = np.frombuffer(pcm, np.int16).astype(np.float32) / 32768
    n = int(len(x) * 16000 / v.config.sample_rate)
    y = np.interp(np.linspace(0, len(x) - 1, n), np.arange(len(x)), x).astype(np.float32)
    # Un po' di silenzio intorno, come dopo il VAD
    return np.concatenate([np.zeros(3200, np.float32), y, np.zeros(4800, np.float32)])


_VOCI_PIPER: dict = {}


class STTFinto:
    """Whisper finto: la frase dalla lunghezza dell'audio (ogni frase della prova ha la sua)."""

    def __init__(self):
        self.testi: dict[int, str] = {}
        self.ricevute = 0
        srv = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_POST(self):
                corpo = self.rfile.read(int(self.headers.get("Content-Length") or 0))
                i = corpo.find(b"RIFF")
                n = 0
                if i >= 0:
                    with wave.open(io.BytesIO(corpo[i:]), "rb") as w:
                        n = w.getnframes()
                srv.ricevute += 1
                testo = ""
                if srv.testi:
                    k = min(srv.testi, key=lambda x: abs(x - n))
                    testo = srv.testi[k] if abs(k - n) < 200 else ""
                data = json.dumps({"text": testo}).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), H)
        self.porta = self.httpd.server_address[1]
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()


STORIA_TESTO = ("C'era una volta una musa che amava le parole. Ogni mattina saliva sul monte "
                "a guardare il mare. Un giorno incontrò un pastore che non sapeva cantare.")


INIZI: list[tuple[str, float]] = []      # (domanda, istante) delle risposte lunghe


def risposta_llm(body):
    """Il «modello»: guarda la storia della conversazione che gli arriva."""
    utente = [m.get("content") or "" for m in body.get("messages") or []
              if m.get("role") == "user"]
    ultima = utente[-1].lower() if utente else ""
    if "storia" in ultima or "tempo" in ultima:
        INIZI.append(("storia" if "storia" in ultima else "tempo", time.monotonic()))
    if "gatto" in ultima and "come si chiama" in ultima:
        nome = next((re.search(r"si chiama (\w+)", u).group(1) for u in utente[:-1]
                     if re.search(r"gatto si chiama \w+", u)), None)
        return {"content": f"Si chiama {nome}." if nome else "Non lo so, non me l'hai detto."}
    if "storia" in ultima:
        return {"content": STORIA_TESTO}
    if "tempo" in ultima:
        return {"content": "Domani sarà sereno con qualche nuvola nel pomeriggio."}
    if re.search(r"\bche ore\b", ultima):
        return {"content": "Sono le dieci e un quarto."}
    return {"content": "Va bene, me lo ricordo."}


class Calliope:
    def __init__(self, tmp: Path, env: dict):
        self.tmp, self.env, self.proc, self.log = tmp, env, None, None

    def avvia(self):
        self.log = open(self.tmp / f"calliope-{int(time.time() * 1000)}.log", "w",
                        encoding="utf-8")
        self.proc = subprocess.Popen([sys.executable, "-u", "-m", "calliope"], cwd=self.tmp,
                                     env=self.env, stdout=self.log, stderr=subprocess.STDOUT)

    def ferma(self):
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(10)
            except subprocess.TimeoutExpired:
                self.proc.kill()
        if self.log:
            self.log.close()

    def testo(self) -> str:
        return "\n".join(p.read_text(encoding="utf-8", errors="replace")
                         for p in sorted(self.tmp.glob("calliope-*.log")))


def registro(tmp: Path) -> list[dict]:
    out = []
    for f in sorted((tmp / "registro").glob("*.jsonl")):
        for r in f.read_text(encoding="utf-8").splitlines():
            try:
                out.append(json.loads(r))
            except ValueError:
                pass
    return out


def prepara_voci(tmp: Path, cfg):
    """speakers.json con Dario (amministra) e Bianca dalle frasi di Piper, e i punteggi."""
    from calliope.speaker_id import SpeakerRegistry
    SpeakerRegistry.PATH = tmp / "speakers.json"
    reg = SpeakerRegistry(cfg)
    for nome in ("Dario", "Bianca"):
        embs = [reg.embed(sintetizza(VOCI[nome], f)) for f in REGISTRA]
        reg.set_voiceprint(nome, embs, admin=(nome == "Dario"))
    reg.save()
    return reg


# Codice d'uscita di una prova saltata per intero (06/10): il runner la conta a parte,
# non come superata (prove/__main__.py)
SALTATA = 77


def main():
    global errori
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass
    from calliope import capacita
    from calliope.config import Config
    voci_ok = all((RADICE / "voices" / v).is_file() for v in list(VOCI.values()) +
                  [CALLIOPE_VOCE])
    cam = RADICE / Config().speaker_model
    if not (capacita.presente("websockets") and voci_ok and cam.is_file()
            and capacita.presente("piper")):
        print("Voci di Piper, CAM++ o websockets assenti: salto la prova delle corsie con "
              "Calliope vera")
        return SALTATA
    from ollama_finto import FakeOllama
    from satellite_finto import SatelliteFinto, pcm_di
    from calliope.satellite.archivio import ArchivioSatelliti

    with tempfile.TemporaryDirectory(prefix="calliope-corsie-",
                                     ignore_cleanup_errors=True) as d:
        tmp = Path(d)
        cfg = Config()
        cfg.speaker_model = str(cam)
        reg = prepara_voci(tmp, cfg)
        # Le frasi, per voce; il Whisper finto le riconosce dalla lunghezza
        stt = STTFinto()
        frasi: dict[tuple[str, str], np.ndarray] = {}
        for chi, testi in (("Dario", [GATTO, DOMANDA, STORIA, ORE]),
                           ("Bianca", [DOMANDA, TEMPO]), ("ospite", [DOMANDA])):
            for t in testi:
                x = sintetizza(VOCI[chi], t)
                while any(abs(len(x) - k) < 400 for k in stt.testi):
                    x = np.concatenate([x, np.zeros(400, np.float32)])
                stt.testi[len(x)] = t
                frasi[(chi, t)] = x
        punteggi = {}
        for (chi, t), x in frasi.items():
            nome, sim = reg.best_match(x)
            punteggi[(chi, t)] = (nome, round(sim, 2))
        soglia = cfg.speaker_id_threshold
        riconosciuti = all((n == chi and s >= soglia) if chi != "ospite" else s < soglia - 0.06
                           for (chi, _), (n, s) in punteggi.items())
        ok("CAM++ sulle voci di Piper: Dario e Bianca riconosciuti, l'ospite no",
           riconosciuti, str({f"{c}:{t[10:24]}": v for (c, t), v in punteggi.items()}))
        if not riconosciuti:
            return 1

        ollama = FakeOllama(modelli=(Config().llm_model,))
        ollama.predefinita = risposta_llm
        ollama.avvia()
        porta_sat = porta_libera()
        arch = ArchivioSatelliti(str(tmp / "memoria.db"))
        _, tok_studio = arch.crea_con_token("studio")
        _, tok_cucina = arch.crea_con_token("cucina")
        arch.close()

        def avvia(parallele: int) -> Calliope:
            righe = {
                "audio_modo": "satellite", "satellite_porta": porta_sat,
                "llm_native_url": f"http://127.0.0.1:{ollama.porta}",
                "stt_motore": "server", "stt_url": f"http://127.0.0.1:{stt.porta}/v1",
                "piper_voice": str(RADICE / "voices" / CALLIOPE_VOCE),
                "speaker_model": str(cam),
                "memory_db": str(tmp / "memoria.db"), "turn_log_dir": str(tmp / "registro"),
                "followup_s": 1.0, "biblioteca_enabled": False, "pc_enabled": False,
                "documenti_enabled": False, "casa_enabled": False, "schermi_enabled": False,
                "agenti_enabled": False, "installa_enabled": False,
                "conversazioni_parallele": parallele, "satelliti_insieme": True,
            }
            (tmp / "calliope.yaml").write_text(json.dumps(righe), encoding="utf-8")
            env = {k: v for k, v in os.environ.items() if not k.startswith("CALLIOPE_")}
            env.update(PYTHONPATH=str(RADICE), PYTHONUTF8="1",
                       CALLIOPE_CONFIG=str(tmp / "calliope.yaml"),
                       CALLIOPE_CONFIG_LOCALE=str(tmp / "nessun-file-locale.yaml"),
                       CALLIOPE_AGENTI_CONFIG=str(tmp / "nessun-file-dgx.yaml"),
                       CALLIOPE_PORTA_ISTANZA=str(porta_libera()),
                       # Come il runner (07/10): niente taratura della voce, che proverebbe i
                       # thread di Piper a ogni avvio (le CALLIOPE_* sopra sono tolte)
                       CALLIOPE_TTS_TARATURA="0")
            cal = Calliope(tmp, env)
            cal.avvia()
            return cal

        url = f"ws://127.0.0.1:{porta_sat}"
        cal = avvia(2)
        studio = cucina = None
        try:
            studio = SatelliteFinto(url, tok_studio, "studio").avvia(90)
            cucina = SatelliteFinto(url, tok_cucina, "cucina").avvia(30)
            ok("due satelliti collegati, una corsia ciascuno",
               studio.ascolta(30) and cucina.ascolta(30)
               and _aspetta(lambda: cal.testo().count("corsia nuova") >= 2, 10),
               "" if cal.testo().count("corsia nuova") >= 2 else cal.testo()[-800:])

            def turno(sat, chi, testo, attesa=20.0):
                t = sat.di(pcm_di(frasi[(chi, testo)]))
                if t is None:
                    return None, None
                r = sat.aspetta_frase(t, attesa)
                sat.aspetta_fine_turno(t, attesa)
                return t, r

            # 1. La conversazione segue la persona
            _, r = turno(studio, "Dario", GATTO)
            ok("Dario nello studio: risponde", r is not None, str(r))
            time.sleep(1.3)                        # finestra di ascolto finita
            _, r = turno(cucina, "Dario", DOMANDA)
            ok("Dario continua dalla cucina: la sua conversazione lo segue",
               r is not None and "Micio" in r[1], str(r))
            time.sleep(1.3)
            _, r = turno(cucina, "Bianca", DOMANDA)
            ok("Bianca in cucina: la sua conversazione, niente gatto di Dario",
               r is not None and "Micio" not in r[1] and "Non lo so" in r[1], str(r))
            time.sleep(1.3)
            _, r = turno(studio, "ospite", DOMANDA)
            ok("un ospite nello studio: la sua conversazione, niente gatto di Dario",
               r is not None and "Non lo so" in r[1], str(r))
            time.sleep(1.3)

            # 2. Insieme, con conversazioni_parallele 2: rispondono tutti e due
            ollama.ritardo_pezzo = 0.4             # ~1,6 s per risposta
            INIZI.clear()
            risultati = {}

            def insieme(sat, chi, testo, k):
                t = sat.di(pcm_di(frasi[(chi, testo)]))
                r = sat.aspetta_frase(t, 30) if t else None
                risultati[k] = (t, r)
                if t:
                    sat.aspetta_fine_turno(t, 30)
            th = [threading.Thread(target=insieme, args=(studio, "Dario", STORIA, "studio")),
                  threading.Thread(target=insieme, args=(cucina, "Bianca", TEMPO, "cucina"))]
            for x in th:
                x.start()
            for x in th:
                x.join(40)
            (ts, rs), (tc, rc) = risultati.get("studio", (None, None)), risultati.get(
                "cucina", (None, None))
            ok("insieme: Dario nello studio e Bianca in cucina hanno la loro risposta",
               rs is not None and rc is not None and "musa" in rs[1] and "sereno" in rc[1],
               f"{rs} / {rc}")
            if rs and rc and ts and tc:
                ls, lc = rs[0] - ts, rc[0] - tc
                print(f"    misura (2 insieme, modello finto ~1,6 s a risposta): prima frase "
                      f"studio {ls:.2f} s, cucina {lc:.2f} s (Piper compreso)")
                inizi = [t for _, t in INIZI]
                ok("con conversazioni_parallele 2 il modello risponde ai due insieme (le "
                   "risposte cominciano entro 1 s, durano 1,6 s)",
                   len(inizi) == 2 and abs(inizi[0] - inizi[1]) < 1.0, str(INIZI))
                coda = [s for _, s in studio.frasi_dopo(ts) + cucina.frasi_dopo(tc)
                        if "un'altra persona" in s]
                ok("nessuna frase della coda sotto il limite", not coda, str(coda))
            ollama.ritardo_pezzo = 0.0
            time.sleep(1.5)

            # 3. La stessa frase sentita dai due satelliti: risponde solo uno
            n_studio, n_cucina = len(studio.frasi), len(cucina.frasi)
            x = pcm_di(frasi[("Dario", ORE)])
            th = [threading.Thread(target=s.di, args=(x,)) for s in (studio, cucina)]
            for t_ in th:
                t_.start()
            for t_ in th:
                t_.join(20)

            def dieci():
                return [s for _, s in studio.frasi[n_studio:] + cucina.frasi[n_cucina:]
                        if "dieci" in s]
            # Si aspettano le condizioni, non un tempo fisso (07/10: con la CPU presa da altro
            # 4 s non bastavano): la risposta arrivata e il doppione scartato dall'altro
            # satellite; poi la fine del turno di chi ha risposto e un margine, perché una
            # seconda risposta avrebbe avuto il tempo di arrivare
            _aspetta(lambda: dieci() and any(r.get("esito") == "doppione"
                                             for r in registro(tmp)), 20)
            for s in (studio, cucina):
                if any("dieci" in x for _, x in s.frasi[n_studio if s is studio else n_cucina:]):
                    s.aspetta_fine_turno(s.frasi[-1][0] - 0.001, 10)
            time.sleep(1.0)
            risposte = dieci()
            ok("la stessa frase da due satelliti nella stessa stanza: una risposta sola",
               len(risposte) == 1, str(risposte))
            righe = registro(tmp)
            ok("registro dei turni: il doppione con la sua regola",
               any(r.get("esito") == "doppione"
                   and "doppione_altro_satellite" in (r.get("regole") or []) for r in righe))
            con = [r for r in righe if r.get("esito") == "risposta"]
            ok("registro dei turni: satellite e conversazione in ogni risposta",
               con and all(r.get("satellite") in ("studio", "cucina")
                           and (r.get("conversazione") or {}).get("tipo") in ("persona",
                                                                              "ospite")
                           for r in con), str([(r.get("satellite"), r.get("conversazione"))
                                               for r in con][:6]))
            ok("registro dei turni: la ripresa di Dario dalla cucina",
               any(r.get("satellite") == "cucina"
                   and (r.get("conversazione") or {}).get("come") == "ripresa" for r in con))
        finally:
            for s in (studio, cucina):
                if s is not None:
                    s.chiudi()
            cal.ferma()
            if errori:
                print("---- uscita di Calliope ----")
                print(cal.testo()[-5000:])

        # 4. Con conversazioni_parallele 1: la seconda aspetta, con la frase della coda
        time.sleep(1.0)
        cal = avvia(1)
        studio = cucina = None
        try:
            studio = SatelliteFinto(url, tok_studio, "studio").avvia(90)
            cucina = SatelliteFinto(url, tok_cucina, "cucina").avvia(30)
            studio.ascolta(30)
            cucina.ascolta(30)
            ollama.ritardo_pezzo = 0.5             # ~2 s per risposta
            INIZI.clear()
            risultati = {}

            def uno(sat, chi, testo, k, ritardo):
                time.sleep(ritardo)
                t = sat.di(pcm_di(frasi[(chi, testo)]))
                risultati[k] = t
                if t:
                    sat.aspetta_fine_turno(t, 40)
            th = [threading.Thread(target=uno, args=(studio, "Dario", STORIA, "studio", 0.0)),
                  threading.Thread(target=uno, args=(cucina, "Bianca", TEMPO, "cucina", 0.3))]
            for x in th:
                x.start()
            for x in th:
                x.join(60)
            tc = risultati.get("cucina")
            frasi_c = [s for _, s in cucina.frasi_dopo(tc)] if tc else []
            # La frase della coda è già sintetizzata (come le frasi d'attesa dei tool): arriva
            # al satellite senza testo, perché non entra nella storia
            ok("oltre il limite: in cucina prima la frase della coda (già pronta), poi la "
               "risposta di Bianca",
               len(frasi_c) >= 2 and frasi_c[0] == ""
               and any("sereno" in s for s in frasi_c[1:]), str(frasi_c[:3]))
            inizi = dict(INIZI)
            ok("…e il modello risponde a Bianca solo dopo aver finito con Dario",
               len(INIZI) == 2 and inizi["tempo"] - inizi["storia"] >= 1.8, str(INIZI))
            ts = risultati.get("studio")
            frasi_s = [s for _, s in studio.frasi_dopo(ts)] if ts else []
            ok("…e la risposta cominciata nello studio non si interrompe",
               any("musa" in s for s in frasi_s) and not any("un'altra persona" in s
                                                           for s in frasi_s), str(frasi_s[:3]))
            ok("registro dei turni: regola coda_risposte e secondi in coda",
               _aspetta(lambda: any("coda_risposte" in (r.get("regole") or [])
                                    and r.get("coda_s") for r in registro(tmp)), 8))
        finally:
            for s in (studio, cucina):
                if s is not None:
                    s.chiudi()
            cal.ferma()
            if errori:
                print("---- uscita di Calliope (limite 1) ----")
                print(cal.testo()[-4000:])
    print(f"\n{'Tutto bene.' if not errori else f'{errori} errori'}")
    return 1 if errori else 0


def _aspetta(cond, timeout=10.0):
    fine = time.monotonic() + timeout
    while time.monotonic() < fine:
        if cond():
            return True
        time.sleep(0.05)
    return cond()


if __name__ == "__main__":
    sys.exit(main())
