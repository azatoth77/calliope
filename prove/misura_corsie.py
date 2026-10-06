"""
Misura: più persone parlano a Calliope insieme da satelliti diversi (06/10/2026, rapporto
docs/ricerche/2026-10-06-conversazione-persona.md). Serve a scegliere
`conversazioni_parallele`.

    python prove/misura_corsie.py --base ~/calliope [--persone 3] [--giri 4] [--parallele 3]

Avvia una **seconda** Calliope (questo codice) in una cartella temporanea, con il modello della
voce, la finestra e Whisper dell'installazione di `--base` (il suo calliope.yaml e
calliope.locale.yaml: stesso `llm_profilo`, stessa `llm_num_ctx`, così Ollama non ricarica il
modello; il servizio vero non si tocca), senza casa, schermi, agenti, biblioteca, archivio,
conversazioni e guardiano. Si collegano `--persone` satelliti finti (prove/satellite_finto.py),
ognuno con una persona registrata (voci di Piper, impronte CAM++ in speakers.json della
cartella temporanea). A ogni giro 1, 2, … `--persone` satelliti dicono insieme una domanda
diversa (audio vero di Piper, trascritto da Whisper), e si misura dalla fine della frase alla
prima frase di Calliope sul satellite (e la frase della coda, se arriva). `--parallele` è
`conversazioni_parallele` della Calliope di prova (3 = nessuna attesa: si vede il modello).

Stampa e salva in `--uscita` (JSON): per ogni numero di persone insieme la prima frase
(mediana, p90, massimo), la prima frase nel registro dei turni (dallo STT in poi, `prima_frase_s`),
i secondi in coda, e `/api/ps` di Ollama prima e dopo (finestra uguale = niente ricarica).
"""
import argparse
import json
import os
import statistics
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

RADICE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RADICE))
sys.path.insert(0, str(RADICE / "prove"))

PERSONE = [("Dario", "it_IT-riccardo-x_low.onnx"), ("Bianca", "it_IT-paola-medium.onnx"),
           ("Marta", "it_IT-serena-medium.onnx")]
DOMANDE = {
    "Dario": ["Calliope, dammi un consiglio per dormire meglio.",
              "Calliope, perché il cielo è azzurro?",
              "Calliope, come posso concentrarmi meglio quando studio?",
              "Calliope, cosa posso regalare a un amico che ama la montagna?",
              "Calliope, dimmi una curiosità sui polpi."],
    "Bianca": ["Calliope, come si prepara il risotto alla milanese?",
              "Calliope, cosa posso cucinare stasera con le zucchine?",
              "Calliope, perché le foglie in autunno cambiano colore?",
              "Calliope, dammi un'idea per una gita di un giorno.",
              "Calliope, dimmi una curiosità sulla luna."],
    "Marta": ["Calliope, come si toglie una macchia di caffè dalla camicia?",
              "Calliope, che differenza c'è tra un rospo e una rana?",
              "Calliope, dammi tre consigli per correre la prima volta.",
              "Calliope, come faccio a ricordarmi meglio i nomi delle persone?",
              "Calliope, dimmi una curiosità sulle api."],
}
REGISTRA = ["Raccontami cosa hai fatto oggi, con calma e senza fretta.",
            "Dimmi qual è il tuo piatto preferito e perché ti piace tanto.",
            "Descrivimi la stanza in cui ti trovi adesso, con tutti i mobili."]


def porta_libera() -> int:
    import socket
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def assoluto(base: Path, p) -> str:
    q = Path(str(p)).expanduser()
    return str(q if q.is_absolute() else base / q)


def sintetizza(path: str, testo: str):
    import numpy as np
    from piper import PiperVoice
    v = _VOCI.get(path) or _VOCI.setdefault(path, PiperVoice.load(path))
    pcm = b"".join(ch.audio_int16_bytes for ch in v.synthesize(testo))
    x = np.frombuffer(pcm, np.int16).astype(np.float32) / 32768
    n = int(len(x) * 16000 / v.config.sample_rate)
    y = np.interp(np.linspace(0, len(x) - 1, n), np.arange(len(x)), x).astype(np.float32)
    return np.concatenate([np.zeros(3200, np.float32), y, np.zeros(4800, np.float32)])


_VOCI: dict = {}


def ps(url: str) -> list:
    import httpx
    try:
        r = httpx.get(url.rstrip("/") + "/api/ps", timeout=3)
        return [{"modello": m.get("name"), "finestra": m.get("context_length"),
                 "scade": m.get("expires_at")} for m in r.json().get("models", [])]
    except Exception as e:  # noqa: BLE001
        return [{"errore": f"{type(e).__name__}"}]


def stat(v: list[float]) -> dict:
    if not v:
        return {}
    s = sorted(v)
    return {"n": len(s), "mediana": round(statistics.median(s), 2),
            "p90": round(s[min(len(s) - 1, int(0.9 * len(s)))], 2), "max": round(s[-1], 2)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="~/calliope", help="la cartella dei dati dell'installazione")
    ap.add_argument("--persone", type=int, default=3)
    ap.add_argument("--giri", type=int, default=4)
    ap.add_argument("--parallele", type=int, default=3)
    ap.add_argument("--uscita", default="")
    ap.add_argument("--tieni", action="store_true", help="non cancellare la cartella temporanea")
    a = ap.parse_args()
    base = Path(a.base).expanduser()
    os.environ["CALLIOPE_CONFIG"] = str(base / "calliope.yaml")
    os.environ["CALLIOPE_CONFIG_LOCALE"] = str(base / "calliope.locale.yaml")
    from calliope.config import load_config
    cwd = os.getcwd()
    os.chdir(base)
    try:
        prod = load_config()
    finally:
        os.chdir(cwd)
    num_ctx = prod.llm_num_ctx
    try:
        salvato = json.loads((base / "contesto.json").read_text(encoding="utf-8"))
        chiave = f"{prod.llm_backend}|{prod.llm_native_url}|{prod.llm_model}"
        num_ctx = int(salvato.get(chiave, {}).get("finestra") or num_ctx)
    except (OSError, ValueError, TypeError):
        pass
    voce_calliope = assoluto(base, prod.piper_voice)
    cam = assoluto(base, prod.speaker_model)
    persone = PERSONE[:max(1, min(a.persone, len(PERSONE)))]
    print(f"[MISURA] modello {prod.llm_model} ({prod.llm_backend}, {prod.llm_native_url}), "
          f"finestra {num_ctx}, STT {prod.stt_motore} {prod.stt_url or ''}, "
          f"{len(persone)} persone, {a.giri} giri, conversazioni_parallele {a.parallele}",
          flush=True)
    risultati = {"modello": prod.llm_model, "finestra": num_ctx, "parallele": a.parallele,
                 "ps_prima": ps(prod.llm_native_url)}
    from calliope.config import Config
    from calliope.satellite.archivio import ArchivioSatelliti
    from calliope.speaker_id import SpeakerRegistry
    from satellite_finto import SatelliteFinto, pcm_di

    tmpdir = tempfile.mkdtemp(prefix="calliope-misura-corsie-")
    tmp = Path(tmpdir)
    cfg = Config()
    cfg.speaker_model = cam
    SpeakerRegistry.PATH = tmp / "speakers.json"
    reg = SpeakerRegistry(cfg)
    voci = {n: assoluto(base, Path("voices") / v) for n, v in persone}
    for nome, path in voci.items():
        reg.set_voiceprint(nome, [reg.embed(sintetizza(path, f)) for f in REGISTRA],
                           admin=(nome == "Dario"))
    reg.save()
    frasi = {(n, d): pcm_di(sintetizza(voci[n], d)) for n, _ in persone for d in DOMANDE[n]}
    arch = ArchivioSatelliti(str(tmp / "memoria.db"))
    token = {n: arch.crea_con_token(f"stanza-{n.lower()}")[1] for n, _ in persone}
    arch.close()
    porta = porta_libera()
    righe = {
        "audio_modo": "satellite", "satellite_indirizzo": "127.0.0.1", "satellite_porta": porta,
        "llm_profilo": prod.llm_profilo, "llm_num_ctx": num_ctx,
        "llm_keep_alive": prod.llm_keep_alive,
        "stt_motore": prod.stt_motore, "stt_url": prod.stt_url,
        "stt_modello": getattr(prod, "stt_modello", None), "stt_correzione": False,
        "piper_voice": voce_calliope, "speaker_model": cam,
        "memory_db": str(tmp / "memoria.db"), "turn_log_dir": str(tmp / "registro"),
        "followup_s": 0.5, "biblioteca_enabled": False, "pc_enabled": False,
        "documenti_enabled": False, "casa_enabled": False, "schermi_enabled": False,
        "agenti_enabled": False, "installa_enabled": False, "conversazioni_enabled": False,
        "minori_enabled": False, "guardiano_enabled": False, "estensioni_enabled": False,
        "archivio_cartella": None, "web_searxng_url": None,
        "conversazioni_parallele": a.parallele, "satelliti_insieme": True,
    }
    righe = {k: v for k, v in righe.items() if v is not None or k in ("archivio_cartella",
                                                                     "web_searxng_url")}
    (tmp / "calliope.yaml").write_text(json.dumps(righe), encoding="utf-8")
    env = {k: v for k, v in os.environ.items() if not k.startswith("CALLIOPE_")}
    env.update(PYTHONPATH=str(RADICE), PYTHONUTF8="1",
               CALLIOPE_CONFIG=str(tmp / "calliope.yaml"),
               CALLIOPE_CONFIG_LOCALE=str(tmp / "nessun-file-locale.yaml"),
               CALLIOPE_AGENTI_CONFIG=str(tmp / "nessun-file-dgx.yaml"),
               CALLIOPE_PORTA_ISTANZA=str(porta_libera()))
    log = open(tmp / "calliope.log", "w", encoding="utf-8")
    proc = subprocess.Popen([sys.executable, "-u", "-m", "calliope"], cwd=tmp, env=env,
                            stdout=log, stderr=subprocess.STDOUT)
    sats = {}
    try:
        for n, _ in persone:
            sats[n] = SatelliteFinto(f"ws://127.0.0.1:{porta}", token[n], n).avvia(180)
        for s in sats.values():
            s.ascolta(60)
        print("[MISURA] Calliope pronta, satelliti collegati", flush=True)
        prossima = {n: 0 for n, _ in persone}
        per_n: dict[int, dict] = {}
        for k in range(1, len(persone) + 1):
            lat, coda_frase = [], []
            for g in range(a.giri):
                chi = [n for n, _ in persone][:k]
                esiti = {}

                def parla(n):
                    d = DOMANDE[n][prossima[n] % len(DOMANDE[n])]
                    t = sats[n].di(frasi[(n, d)])
                    if t is None:
                        return
                    r = None
                    fine = time.monotonic() + 60
                    while time.monotonic() < fine:          # la prima frase con il testo
                        r = sats[n].aspetta_frase(t, max(0.1, fine - time.monotonic()))
                        if r is None or r[1]:
                            break
                        coda_frase.append(r[0] - t)
                        t2 = r[0]
                        r = sats[n].aspetta_frase(t2, max(0.1, fine - time.monotonic()))
                        break
                    esiti[n] = (t, r)
                    sats[n].aspetta_fine_turno(t, 90)
                th = [threading.Thread(target=parla, args=(n,)) for n in chi]
                for x in th:
                    x.start()
                for x in th:
                    x.join(150)
                for n in chi:
                    prossima[n] += 1
                    t, r = esiti.get(n, (None, None))
                    if t and r:
                        lat.append(r[0] - t)
                        print(f"   {k} insieme, giro {g + 1}: {n} prima frase "
                              f"{r[0] - t:.2f} s «{r[1][:50]}»", flush=True)
                    else:
                        print(f"   {k} insieme, giro {g + 1}: {n} nessuna risposta", flush=True)
                time.sleep(1.5)                           # finestre di ascolto finite
            per_n[k] = {"prima_frase_satellite": stat(lat), "frase_coda": stat(coda_frase)}
        risultati["per_persone"] = per_n
    finally:
        for s in sats.values():
            s.chiudi()
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(15)
            except subprocess.TimeoutExpired:
                proc.kill()
        log.close()
    # Il registro dei turni: prima frase dallo STT in poi, coda
    righe_reg = []
    for f in sorted((tmp / "registro").glob("*.jsonl")):
        for r in f.read_text(encoding="utf-8").splitlines():
            try:
                righe_reg.append(json.loads(r))
            except ValueError:
                pass
    risposte = [r for r in righe_reg if r.get("esito") == "risposta"]
    risultati["registro"] = {
        "risposte": len(risposte),
        "prima_frase_s": stat([r["prima_frase_s"] for r in risposte if r.get("prima_frase_s")]),
        "stt_s": stat([r["stt_s"] for r in risposte if r.get("stt_s")]),
        "coda_s": stat([r["coda_s"] for r in risposte if r.get("coda_s")]),
        "voce": [((r.get("voce") or {}).get("nome"), (r.get("voce") or {}).get("modo"))
                 for r in risposte][:12]}
    risultati["ps_dopo"] = ps(prod.llm_native_url)
    print(json.dumps(risultati, ensure_ascii=False, indent=1))
    if a.uscita:
        Path(a.uscita).write_text(json.dumps(risultati, ensure_ascii=False, indent=1),
                                  encoding="utf-8")
    if not a.tieni:
        import shutil
        shutil.rmtree(tmp, ignore_errors=True)
    else:
        print(f"[MISURA] cartella: {tmp}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
