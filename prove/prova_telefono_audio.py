import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

"""L'audio del microfono della web app del telefono e la sua diagnostica (03/10/2026).

Dal telefono vero (iPhone, WebKit) l'audio arrivava rovinato: parole in islandese da Whisper,
impronta vocale a 0,1–0,2. Questa prova:

A secco (sempre):
- `telefono_diagnostica`: corpo malformato rifiutato (magia, JSON, segmenti, troncato, byte in
  più); un audio giusto non dà problemi; lo stesso audio al ritmo sbagliato (×1,5, il caso
  iOS) e con frequenze diverse tra traccia e contesto viene segnalato (ritmo, tono, frequenze);
  buchi, blocchi persi, segnale muto; pulizia delle prove vecchie;
- l'endpoint POST /telefono/api/diagnostica con i server veri: senza token 401, telefono non
  personale 403, troppo grande 413, troppe prove 429, giusto → riassunto e WAV salvati.

Nel browser vero (Edge o Chromium senza finestra, microfono finto con un WAV di Piper a 44,1 e
48 kHz; senza browser o voci si salta): «Prova il microfono» dalla pagina, e il server confronta
ciò che riceve con il WAV d'origine (correlazione, durata, ritmo); anche con il contesto del
microfono forzato a 22 050 Hz (il caso iOS: contesto a una frequenza diversa dalla traccia),
che la pagina deve rifare alla frequenza della traccia. Con le correzioni del browser accese e
spente (misura). Con faster-whisper e il modello «small» in cache, la frase ricevuta si
trascrive giusta (e, per confronto, quella accelerata come su iOS no).
"""

import json
import shutil
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

import numpy as np

RADICE = Path(__file__).resolve().parent.parent
TMP = Path(tempfile.mkdtemp(prefix="calliope-telaudio-"))
ERRORI = []
MISURE = {}
FRASE = "Calliope, che ore sono? Oggi è una bella giornata."


def verifica(nome, ok, dettaglio=""):
    print(("ok  " if ok else "NO  ") + nome + (f"  ({dettaglio})" if dettaglio else ""), flush=True)
    if not ok:
        ERRORI.append(nome)


def corpo(prove: list[dict], segmenti: list[tuple[dict, np.ndarray]], **extra) -> bytes:
    meta = {"versione": 1, "ua": "prova", "prove": prove,
            "segmenti": [s for s, _ in segmenti], **extra}
    js = json.dumps(meta).encode()
    dati = b"".join((np.clip(x, -1, 1) * 32767).astype("<i2").tobytes() for _, x in segmenti)
    return b"CDG1" + len(js).to_bytes(4, "big") + js + dati


def voce_finta(sr: int, secondi: float, f0: float = 120.0) -> np.ndarray:
    """Un «parlato» sintetico: impulsi glottali a f0 filtrati da due formanti, a sillabe."""
    n = int(sr * secondi)
    t = np.arange(n) / sr
    imp = np.zeros(n, np.float32)
    imp[(np.arange(0, secondi, 1 / f0) * sr).astype(int)] = 1.0
    x = np.zeros(n, np.float32)
    for f, bw in ((700, 110), (1200, 120)):
        r = np.exp(-np.pi * bw / sr)
        a1, a2 = -2 * r * np.cos(2 * np.pi * f / sr), r * r
        y = np.zeros(n, np.float32)
        for i in range(2, n):
            y[i] = imp[i] - a1 * y[i - 1] - a2 * y[i - 2]
        x += y
    inv = (0.5 + 0.5 * np.sin(2 * np.pi * 3 * t)) ** 2
    x = x * inv
    return (0.3 * x / np.max(np.abs(x))).astype(np.float32)


def parte_secco():
    from calliope.config import Config
    from calliope.schermi import telefono_diagnostica as D
    cfg = Config()
    cfg.config_dir = str(TMP / "secco")
    cfg.speaker_model = str(TMP / "manca.onnx")
    # ── formato ──
    for nome, dati in (("magia sbagliata", b"XXXX\x00\x00\x00\x02{}"),
                       ("JSON rotto", b"CDG1\x00\x00\x00\x03{x}"),
                       ("niente segmenti", corpo([], [])),
                       ("frequenza assurda", corpo([{}], [({"prova": 0, "tipo": "uscita", "rate": 10,
                                                             "campioni": 0}, np.zeros(0))])),
                       ("tipo sconosciuto", corpo([{}], [({"prova": 0, "tipo": "x", "rate": 16000,
                                                            "campioni": 0}, np.zeros(0))]))):
        try:
            D.leggi_corpo(dati)
            verifica(f"corpo rifiutato: {nome}", False)
        except D.ErroreDiagnostica:
            verifica(f"corpo rifiutato: {nome}", True)
    x = np.zeros(1600, np.float32)
    buono = corpo([{}], [({"prova": 0, "tipo": "uscita", "rate": 16000, "campioni": 1600}, x)])
    for nome, dati in (("troncato", buono[:-10]), ("byte in più", buono + b"\x00\x00")):
        try:
            D.leggi_corpo(dati)
            verifica(f"corpo rifiutato: {nome}", False)
        except D.ErroreDiagnostica:
            verifica(f"corpo rifiutato: {nome}", True)

    # ── audio giusto ──
    s48 = voce_finta(48000, 4.0)
    u16 = D.ricampiona(s48, 48000, 16000)
    pm = {"etichetta": "giusto", "durata_vera_s": 4.0, "durata_contesto_s": 4.0, "quanti": 1500,
          "quanti_zero": 0, "quanti_doppi": 0, "persi": 0, "rate_contesto": 48000,
          "traccia": {"sampleRate": 48000}, "stato_contesto": "running"}
    segs = [({"prova": 0, "tipo": "grezzo", "rate": 48000, "campioni": len(s48)}, s48),
            ({"prova": 0, "tipo": "uscita", "rate": 16000, "campioni": len(u16)}, u16)]
    m = D.misura({"prove": [pm]}, segs, cfg)[0]
    # (Silero non riconosce come voce il parlato sintetico: quel controllo qui non conta)
    p = [x for x in D.problemi(m, cfg) if "VAD" not in x]
    verifica("audio giusto: nessun problema", not p, "; ".join(p))
    verifica("audio giusto: tono di una voce adulta (~120 Hz)",
             m["tono_hz"] is not None and 100 <= m["tono_hz"] <= 140, str(m["tono_hz"]))
    verifica("audio giusto: uscita = ingresso ricampionato", m["uscita_uguale_grezzo"] > 0.98,
             str(m["uscita_uguale_grezzo"]))

    # ── il caso iOS: hardware a 24 kHz sotto un contesto a 48 kHz che crede di essere a 48 ──
    # (l'audio letto a ritmo ×2, la voce un'ottava sopra), e frequenze diverse
    veloce = D.ricampiona(s48, 48000, 24000)          # 4 s di voce in 2 s: ×2
    u_vel = D.ricampiona(veloce, 48000, 16000)
    pm2 = dict(pm, etichetta="iOS", durata_vera_s=4.0, durata_contesto_s=2.0,
               traccia={"sampleRate": 24000})
    segs2 = [({"prova": 0, "tipo": "grezzo", "rate": 48000, "campioni": len(veloce)}, veloce),
             ({"prova": 0, "tipo": "uscita", "rate": 16000, "campioni": len(u_vel)}, u_vel)]
    m2 = D.misura({"prove": [pm2]}, segs2, cfg)[0]
    p2 = " · ".join(D.problemi(m2, cfg))
    verifica("caso iOS: frequenze diverse segnalate", "registra a 24000 Hz" in p2, p2)
    verifica("caso iOS: ritmo sbagliato segnalato", "ritmo sbagliato" in p2, p2)
    verifica("caso iOS: voce troppo acuta (audio accelerato)",
             m2["tono_hz"] is not None and m2["tono_hz"] > 200, str(m2["tono_hz"]))

    # ── buchi, blocchi persi, muto ──
    pm3 = dict(pm, quanti_zero=100, persi=3, scartati_inferenza=2)
    muto = np.zeros(64000, np.float32)
    segs3 = [({"prova": 0, "tipo": "uscita", "rate": 16000, "campioni": len(muto)}, muto)]
    p3 = " · ".join(D.problemi(D.misura({"prove": [pm3]}, segs3, cfg)[0], cfg))
    verifica("buchi, blocchi persi e scartati, segnale muto segnalati",
             all(k in p3 for k in ("buchi", "3 blocchi persi", "2 blocchi scartati", "quasi muto")), p3)
    pm4 = dict(pm, durata_contesto_s=4.0)
    corto = u16[:len(u16) // 2]
    segs4 = [({"prova": 0, "tipo": "uscita", "rate": 16000, "campioni": len(corto)}, corto)]
    p4 = " · ".join(D.problemi(D.misura({"prove": [pm4]}, segs4, cfg)[0], cfg))
    verifica("metà dei blocchi a 16 kHz mancanti: segnalato", "escono 2,00 s su 4,00 s" in p4, p4)

    # ── salvataggio e pulizia ──
    esito = D.analizza(cfg, corpo([pm], segs), "telefono di Dario")
    dove = D.cartella(cfg) / esito["cartella"]
    wav = sorted(p.name for p in dove.glob("*.wav"))
    verifica("analizza: WAV, meta.json e riassunto salvati",
             wav == ["prova1-grezzo-48000.wav", "prova1-uscita-16000.wav"]
             and (dove / "meta.json").is_file() and (dove / "riassunto.txt").is_file(), str(wav))
    vecchia = D.cartella(cfg) / "20200101-000000-vecchia"
    vecchia.mkdir()
    os.utime(vecchia, (time.time() - 30 * 86400,) * 2)
    for i in range(D.DIAG_MAX + 3):
        (D.cartella(cfg) / f"20990101-0000{i:02d}-x").mkdir()
    D.pulisci(D.cartella(cfg))
    rimaste = [p.name for p in D.cartella(cfg).iterdir()]
    verifica("pulizia: via le prove scadute e le più vecchie oltre il tetto",
             "20200101-000000-vecchia" not in rimaste and len(rimaste) == D.DIAG_MAX,
             f"{len(rimaste)} rimaste")


# ───────────────────────────── endpoint ─────────────────────────────
def post(url, dati: bytes, token: str | None):
    h = {"Content-Type": "application/octet-stream"}
    if token:
        h["Authorization"] = "Bearer " + token
    req = urllib.request.Request(url, data=dati, headers=h, method="POST")
    apri = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with apri.open(req, timeout=30) as r:
            return r.status, json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}")
    except (ConnectionResetError, ConnectionAbortedError, BrokenPipeError):
        return 0, {}                   # il server ha risposto e chiuso prima della fine dell'invio
    except urllib.error.URLError as e:
        # Su Linux (DGX, 04/10) lo stesso reset arriva avvolto in URLError
        if isinstance(e.reason, (ConnectionResetError, ConnectionAbortedError, BrokenPipeError)):
            return 0, {}
        raise


def parte_reset():
    """post() con un server che chiude con un reset a metà invio: (0, {}) e non un'eccezione,
    sia su Windows (ConnectionResetError) sia su Linux (dentro URLError, 04/10)."""
    import socket
    import struct
    import threading
    srv = socket.socket()
    srv.bind(("127.0.0.1", 0))
    srv.listen(1)

    def chiudi_con_reset():
        try:
            c, _ = srv.accept()
            c.recv(1024)
            c.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER, struct.pack("ii", 1, 0))
            c.close()
        except OSError:
            pass
    t = threading.Thread(target=chiudi_con_reset, daemon=True)
    t.start()
    try:
        st, r = post(f"http://127.0.0.1:{srv.getsockname()[1]}/x", b"\0" * (8 << 20), None)
        verifica("post: reset del server a metà invio = (0, {}), anche dentro URLError",
                 (st, r) == (0, {}), str(st))
    except Exception as e:  # noqa: BLE001
        verifica("post: reset del server a metà invio = (0, {}), anche dentro URLError", False,
                 f"{type(e).__name__}: {e}")
    finally:
        t.join(5)
        srv.close()


def abbina_telefono(amb, personale: bool) -> str:
    r = amb.srv.archivio.nuova_richiesta(personale_chiesto="Dario" if personale else None)
    res = amb.srv.archivio.abbina(r["codice"], "telefono",
                                  proprietario="id-dario" if personale else None,
                                  proprietario_nome="Dario" if personale else None,
                                  nome="telefono di dario" if personale else "telefono ospite")
    assert res["ok"], res
    return r["richiesta"]


def parte_endpoint(amb):
    from calliope.schermi import telefono, telefono_diagnostica as D
    url = amb.url + "/telefono/api/diagnostica"
    s = voce_finta(16000, 2.0)
    dati = corpo([{"etichetta": "x", "durata_vera_s": 2, "durata_contesto_s": 2}],
                 [({"prova": 0, "tipo": "uscita", "rate": 16000, "campioni": len(s)}, s)])
    st, _ = post(url, dati, None)
    verifica("endpoint: senza token 401", st == 401, str(st))
    st, _ = post(url, dati, "token-inventato")
    verifica("endpoint: token sconosciuto 401", st == 401, str(st))
    ospite = abbina_telefono(amb, personale=False)
    st, r = post(url, dati, ospite)
    verifica("endpoint: telefono non personale 403", st == 403, f"{st} {r.get('errore')}")
    tok = abbina_telefono(amb, personale=True)
    st, r = post(url, b"CDG1" + b"\x00" * (D.MAX_BYTE + 10), tok)
    verifica("endpoint: troppo grande 413 (o connessione chiusa durante l'invio)",
             st in (413, 0), str(st))
    st, r = post(url, b"rotto", tok)
    verifica("endpoint: corpo rotto 400", st == 400, str(st))
    st, r = post(url, dati, tok)
    verifica("endpoint: prova giusta, con riassunto e cartella",
             st == 200 and r.get("ok") and r.get("riassunto") and r.get("cartella"),
             f"{st} {r.get('errore')}")
    for _ in range(telefono.DIAG_PER_10_MIN):
        st, r = post(url, dati, tok)
    verifica("endpoint: troppe prove 429", st == 429, str(st))
    return tok


# ───────────────────────────── browser ─────────────────────────────
def allinea(ricevuto: np.ndarray, sorgente: np.ndarray) -> tuple[float, int]:
    """Correlazione normalizzata migliore tra il ricevuto e il WAV d'origine ripetuto in
    loop (come lo ripete il microfono finto), e lo scarto."""
    P = len(sorgente)
    n = len(ricevuto)
    lungo = np.tile(sorgente, int(np.ceil((n + P) / P)) + 1)[:n + P]
    m = 1 << int(np.ceil(np.log2(len(lungo) + n)))
    c = np.fft.irfft(np.fft.rfft(lungo, m) * np.conj(np.fft.rfft(ricevuto, m)), m)[:P]
    k = int(np.argmax(c))
    seg = lungo[k:k + n]
    den = float(np.sqrt(np.dot(seg, seg) * np.dot(ricevuto, ricevuto)))
    return (float(np.dot(seg, ricevuto)) / den if den > 0 else 0.0), k


def whisper():
    try:
        from faster_whisper import WhisperModel
        return WhisperModel("small", device="cpu", compute_type="int8", local_files_only=True)
    except Exception as e:  # noqa: BLE001
        print(f"SALTATA IN PARTE: faster-whisper «small» non disponibile in cache: {e}; trascrizione saltata")
        return None


def trascrivi(modello, x: np.ndarray, lingua=None) -> str:
    segs, info = modello.transcribe(x.astype(np.float32), language=lingua, beam_size=5)
    return " ".join(s.text.strip() for s in segs).strip()


def parole_ok(testo: str) -> float:
    import re
    att = set(re.findall(r"\w+", FRASE.lower()))
    got = set(re.findall(r"\w+", testo.lower()))
    return len(att & got) / len(att)


def parte_browser(amb, tok):
    from prova_telefono_pagina import Pagina, browser, scrivi_wav, sintetizza
    from calliope.schermi import telefono_diagnostica as D
    exe = browser()
    if exe is None:
        print("SALTATA IN PARTE: Nessun Edge né Chromium: parte nel browser saltata.")
        return
    frasi = sintetizza([FRASE])
    if frasi is None:
        print("SALTATA IN PARTE: Nessuna voce di Piper in voices/: parte nel browser saltata.")
        return
    f16 = frasi[FRASE]
    pausa = np.random.default_rng(3).standard_normal(16000).astype(np.float32) * 3e-4
    sorg16 = np.concatenate([f16, pausa])                      # un giro del loop, a 16 kHz
    mod = whisper()
    if mod is not None:
        t = trascrivi(mod, f16, "it")
        MISURE["whisper_originale"] = t
        # Per confronto, la stessa frase come la riceveva Calliope dal telefono se l'hardware
        # va a 24 kHz sotto un contesto a 48 kHz (ritmo ×2), senza lingua come whisper.cpp -l
        # auto e con -l it
        veloce = D.ricampiona(f16, 16000, 8000)
        MISURE["whisper_accelerata_x2_auto"] = trascrivi(mod, veloce)
        MISURE["whisper_accelerata_x2_it"] = trascrivi(mod, veloce, "it")
        lento = D.ricampiona(f16, 16000, 24000)
        MISURE["whisper_rallentata_x1_5_it"] = trascrivi(mod, lento, "it")

    casi = [("48 kHz", 48000, None), ("44,1 kHz", 44100, None),
            ("48 kHz, contesto forzato a 22 050 Hz (caso iOS)", 48000, 22050)]
    for nome, rate, forza in casi:
        sorg = D.ricampiona(sorg16, 16000, rate)
        wav = TMP / f"mic-{rate}.wav"
        scrivi_wav(wav, sorg, rate)
        opz = ("--use-fake-ui-for-media-stream", "--use-fake-device-for-media-stream",
               f"--use-file-for-fake-audio-capture={wav}")
        prof = f"p-{rate}-{forza}"
        pag = Pagina(exe, amb.url + "/telefono/", opz, profilo=prof)
        try:
            # Il token del telefono personale nella pagina, poi si ricarica
            pag.valuta(f"localStorage.setItem('calliope.telefono.token', {json.dumps(tok)}); 1")
            pag._chiama("Page.reload")
            t0 = time.monotonic()
            while time.monotonic() - t0 < 15 and not pag.valuta(
                    "!!(window.calliopeTelefono && window.calliopeTelefono.st.token)"):
                time.sleep(0.2)
            if forza:
                pag.valuta(f"window.calliopeTelefono.opzioniMic.forzaRate = {forza}; 1")
            r = pag.valuta(
                "window.calliopeTelefono.diagnostica({secondi: 8, prove: ["
                "{etichetta: 'con correzioni', vincoli: {echoCancellation: true, noiseSuppression: true, autoGainControl: true}},"
                "{etichetta: 'senza correzioni', vincoli: {echoCancellation: false, noiseSuppression: false, autoGainControl: false}}]})"
                ".then(r => r && {ok: r.ok, esito: r.esito, errore: r.errore, stato: r.stato})",
                timeout=90)
            ok = bool(r and r.get("ok"))
            verifica(f"{nome}: «Prova il microfono» arriva al server", ok, json.dumps(r)[:300])
            if not ok:
                continue
            testo = pag.valuta("document.getElementById('diag-esito').textContent") or ""
            verifica(f"{nome}: la pagina mostra il riassunto", "Esito:" in testo, testo[-120:])
            dove = D.cartella(amb.cfg) / r["esito"]["cartella"]
            meta = json.loads((dove / "meta.json").read_text(encoding="utf-8"))
            for i, mis in enumerate(meta["misure"]):
                pm = meta["meta"]["prove"][i]
                u = load_wav(dove / f"prova{i + 1}-uscita-16000.wav")
                # Correlazione a finestre di 1 s (mediana): il microfono finto di Chromium
                # senza finestra salta ogni tanto 6–8 ms del file (lo scarto cambia a gradini
                # anche nel segnale grezzo), e un confronto unico su 8 s ne soffrirebbe
                fin = [allinea(u[j:j + 16000], sorg16) for j in range(0, len(u) - 15999, 16000)]
                c = float(np.median([f[0] for f in fin])) if fin else 0.0
                k = (fin[0][1] if fin else 0)
                dur = len(u) / 16000
                MISURE[f"{rate}{'-forzato' if forza else ''}-{mis['etichetta']}"] = {
                    "corr": round(c, 3), "durata_s": round(dur, 2), "contesto_s": mis["durata_contesto_s"],
                    "vera_s": mis["durata_vera_s"], "rate_contesto": mis["rate_contesto"],
                    "rate_traccia": mis["rate_traccia"], "ritmo": mis["ritmo"],
                    "rms_db": mis.get("rms_uscita_db"), "tono": mis.get("tono_hz"),
                    "ricostruito": pm.get("ricostruito"), "problemi": D.problemi(mis, amb.cfg)}
                senza = mis["etichetta"] == "senza correzioni"
                verifica(f"{nome}, {mis['etichetta']}: durata giusta (16 kHz contro orologio)",
                         abs(dur - mis["durata_contesto_s"]) < 0.1 and abs(mis["ritmo"] - 1) < 0.05,
                         f"{dur:.2f} s a 16 kHz, {mis['durata_contesto_s']} s di contesto, "
                         f"{mis['durata_vera_s']} s veri")
                # Senza correzioni il segnale deve essere quello del file; con le correzioni
                # (AGC, soppressione del rumore) Chromium lo cambia un po'
                verifica(f"{nome}, {mis['etichetta']}: contenuto uguale al WAV d'origine",
                         c > (0.95 if senza else 0.6), f"correlazione {c:.3f}")
                if forza:
                    verifica(f"{nome}: il contesto rifatto alla frequenza della traccia",
                             pm.get("ricostruito") == 1 and mis["rate_contesto"] == mis["rate_traccia"],
                             f"contesto {mis['rate_contesto']}, traccia {mis['rate_traccia']}, "
                             f"{pm.get('motivo_ricostruzione')}")
                if mod is not None and senza:
                    i0 = (len(sorg16) - k) % len(sorg16)
                    if i0 + len(f16) > len(u):
                        i0 = max(0, i0 - len(sorg16))
                    pezzo = u[i0:i0 + len(f16) + 1600]
                    t = trascrivi(mod, pezzo, "it")
                    MISURE[f"whisper-{rate}{'-forzato' if forza else ''}"] = t
                    verifica(f"{nome}: Whisper trascrive la frase giusta", parole_ok(t) >= 0.7, t)
        finally:
            for riga in pag.log:
                print("   [browser] " + riga)
            errori = [x for x in pag.log if x.startswith(("ECCEZIONE", "ERROR"))
                      and "onnxruntime" not in x and "/telefono/ort/" not in x
                      and "404" not in x]
            verifica(f"{nome}: nessun errore JavaScript", not errori, "; ".join(errori)[:300])
            pag.chiudi()


def load_wav(p: Path) -> np.ndarray:
    import wave
    with wave.open(str(p)) as w:
        return np.frombuffer(w.readframes(w.getnframes()), "<i2").astype(np.float32) / 32768


def main() -> int:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    parte_secco()
    parte_reset()
    import prova_telefono_pagina as P
    P.TMP = TMP
    amb = P.Ambiente()
    try:
        tok = parte_endpoint(amb)
        if "--secco" not in sys.argv:
            # Il limite di prove: un telefono nuovo per il browser
            tok = abbina_telefono(amb, personale=True)
            parte_browser(amb, tok)
    finally:
        amb.chiudi()
        if os.environ.get("CALLIOPE_PROVA_TIENI"):
            print(f"File tenuti in {TMP}")
        else:
            shutil.rmtree(TMP, ignore_errors=True)
    print("\nMisure: " + json.dumps(MISURE, ensure_ascii=False, indent=1))
    print("\nTutto bene." if not ERRORI else f"\n{len(ERRORI)} prove non riuscite.")
    return 1 if ERRORI else 0


if __name__ == "__main__":
    sys.exit(main())
