"""Misura dell'eco della stanza sul portatile (14/10, conversazione di stanza, passo 5).

Progetto docs/ricerche/2026-10-13-conversazione-di-stanza.md § 5.3; passi a mano e telefono in
prove/manuali/misura-eco-stanza.md. NON fa parte del runner: si lancia a mano, con microfono e
casse veri, e senza Piper o Whisper esce con 77.

Sul portatile fa esattamente quello che fa il satellite con `stanza_durante_voce` acceso: il
microfono (stesso `input_device`, in MME con la cancellazione dell'eco di Windows), il
rubinetto della stanza con il suo VAD (`AscoltoStanza`, `durante_voce` acceso), le frasi di
Calliope suonate dal `Riproduttore` del satellite (che segna la frase che suona, `voce_ora`).
Ogni segmento si trascrive con Whisper come la stanza (senza prompt) e passa dal filtro
dell'eco del server (`calliope.stanza.eco.filtra`), con le frasi che suonavano e i loro tempi.

    python prove/manuali/misura_eco_stanza.py --scenario muto|lettura|chiacchiera
           [--frasi 20] [--senza-voce] [--campp] [--salva privato/eco-stanza]

- `muto`: Calliope dice il copione (20 risposte di fantasia) e nessuno parla. Tutto ciò che
  resta nelle righe è eco: **eco residua** = parole rimaste ogni 100 parole dette (obiettivo
  < 2), **righe false** = righe tenute (obiettivo 0). Anche gli stessi numeri senza il filtro.
- `lettura`: una persona legge ad alta voce il testo stampato sullo schermo mentre Calliope
  parla. **Parole recuperate**: WER del testo letto contro le righe tenute; con `--senza-voce`
  la stessa lettura a Calliope muta (il riferimento). Eco residua: parole delle righe che sono
  di lei e non del testo letto.
- `chiacchiera`: due persone chiacchierano mentre Calliope parla. Righe tenute, parole tolte,
  eco residua stimata (parole delle righe che combaciano con lei).
- `--campp`: per ogni segmento la similitudine CAM++ con le frasi di Calliope che suonavano
  (il segnale b del § 5.3, oggi non usato: si rimisura con l'eco vera).
- `--salva DIR`: i numeri in DIR/misura-AAAAMMGG-HHMM-<scenario>.json e, solo con
  `--audio`, i segmenti in wav (adulti che lo sanno: DIR va in privato/, fuori da git). Le
  trascrizioni non si scrivono mai su disco senza `--testi`.
- `--a-secco [--eco-db -30]`: senza microfono né casse, un'eco **simulata** (la voce che esce
  dalle casse finte torna nel microfono finto filtrata in banda, con un riverbero breve e
  attenuata di `--eco-db`, come un residuo della cancellazione) e, per `lettura` e
  `chiacchiera`, le persone con altre voci di Piper (riccardo, paola). Serve a provare il
  giro intero (VAD, Whisper, filtro) e a confrontare le modifiche al filtro; non sostituisce
  la misura vera.
"""
import datetime
import difflib
import json
import os
import sys
import threading
import time
import wave
from pathlib import Path

RADICE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RADICE))
SALTA = 77

# Il copione: 20 risposte di fantasia, lunghe come quelle vere (1–3 frasi)
COPIONE = [
    "Domani a Borgo Lieto ci sarà il sole, con diciannove gradi di massima.",
    "Ho aggiunto il latte e le uova alla lista della spesa.",
    "Il promemoria per la riunione di giovedì è alle dieci e mezza.",
    "La capitale dell'Australia è Canberra, non Sydney come pensano in molti.",
    "Sono le otto e un quarto. Hai ancora tempo per il caffè.",
    "Ho acceso la luce del soggiorno al cinquanta per cento.",
    "Il treno per Valfonda parte alle sette e quaranta dal binario tre.",
    "Una tazza di farina pesa più o meno centoventi grammi.",
    "Nel calendario di sabato c'è la partita di Nicola alle quattro.",
    "Il film comincia alle nove, dura circa due ore.",
    "Ho messo un timer di dodici minuti per la pasta.",
    "La temperatura in camera è di ventuno gradi e mezzo.",
    "Mercurio è il pianeta più vicino al Sole e il più piccolo del sistema solare.",
    "Ti ricordo di innaffiare le piante del balcone prima di cena.",
    "La parola del giorno è serendipità: trovare qualcosa di bello per caso.",
    "Ho spento la radio in cucina e chiuso le tapparelle.",
    "Per fare il pane servono farina, acqua, lievito e un pizzico di sale.",
    "Il negozio di ferramenta chiude alle sette e mezza di sera.",
    "Domenica è prevista pioggia leggera nel pomeriggio, porta l'ombrello.",
    "Ecco fatto, la sveglia è puntata per domani alle sei e quarantacinque.",
]
# Due persone che chiacchierano (scenario chiacchiera, solo a secco: dal vivo parlano loro)
CHIACCHIERA = [
    "Allora sabato partiamo presto per la gita al lago?",
    "Sì, io direi alle otto, così troviamo parcheggio.",
    "Porto io i panini, tu pensi alle bibite.",
    "Va bene, e se piove andiamo al museo in città.",
    "Ricordati di caricare la macchina fotografica stasera.",
    "Ci sentiamo domani per gli ultimi dettagli.",
]
# Il testo noto da leggere ad alta voce (scenario lettura)
LETTURA = (
    "C'era una volta un piccolo paese in cima a una collina, dove ogni mattina il fornaio "
    "apriva la bottega prima dell'alba. I bambini passavano a prendere il pane caldo prima di "
    "andare a scuola, e il fornaio regalava sempre un biscotto a chi lo salutava per primo. "
    "Un giorno arrivò in paese un viaggiatore con un cappello enorme e una valigia piena di "
    "mappe. Chiese la strada per il lago, ma nessuno sapeva che ci fosse un lago da quelle "
    "parti. Il viaggiatore sorrise, aprì una mappa sul bancone e indicò un punto azzurro "
    "proprio dietro la collina."
)


def opzioni(argv):
    o, i = {"_": []}, 0
    while i < len(argv):
        a = argv[i]
        if a.startswith("--"):
            k = a[2:].replace("-", "_")
            if i + 1 < len(argv) and not argv[i + 1].startswith("--"):
                o[k] = argv[i + 1]
                i += 2
            else:
                o[k] = True
                i += 1
        else:
            o["_"].append(a)
            i += 1
    return o


def wer(rif: list[str], ipo: list[str]) -> float:
    """Word error rate con la distanza di modifica sulle parole normalizzate."""
    n, m = len(rif), len(ipo)
    d = list(range(m + 1))
    for i in range(1, n + 1):
        prima, d[0] = d[0], i
        for j in range(1, m + 1):
            c = min(d[j] + 1, d[j - 1] + 1, prima + (rif[i - 1] != ipo[j - 1]))
            prima, d[j] = d[j], c
    return d[m] / max(1, n)


class Simulazione:
    """A secco: le casse finte rimandano la voce al microfono finto come eco residua, più le
    persone (audio a 16 kHz messo in coda dall'inizio) e un filo di rumore."""

    def __init__(self, eco_db: float):
        import collections
        import numpy as np
        self.np = np
        self.g = 10 ** (eco_db / 20)
        self.eco = collections.deque()
        self.persone = np.zeros(0, np.float32)
        self.lock = threading.Lock()
        self.rng = np.random.default_rng(3)
        try:
            from scipy.signal import butter
            self.filtro = butter(4, [250 / 8000, 3800 / 8000], btype="band")
        except Exception:  # noqa: BLE001 — senza scipy niente banda
            self.filtro = None
        t = np.arange(int(0.2 * 16000)) / 16000
        self.h = self.rng.normal(0, 1, len(t)) * np.exp(-t / 0.05)
        self.h[0] = 4.0
        self.h /= np.abs(self.h).sum() / 4

    def _eco(self, x16):
        np = self.np
        if self.filtro is not None:
            from scipy.signal import lfilter
            x16 = lfilter(*self.filtro, x16)
        y = np.convolve(x16, self.h)[: len(x16)]
        return (np.tanh(2 * y) / 2 * self.g).astype(np.float32)

    def uscita(self, samplerate, channels, dtype, device):
        sim = self

        class Uscita:
            latency = 0.05

            def __init__(self):
                self.samplerate = samplerate

            def start(self):
                pass

            stop = close = abort = start

            def write(self, data):
                np = sim.np
                x = np.frombuffer(bytes(data), "<i2").astype(np.float32) / 32768
                n = int(len(x) * 16000 / self.samplerate)
                if n:
                    x16 = np.interp(np.linspace(0, len(x) - 1, n), np.arange(len(x)), x)
                    with sim.lock:
                        sim.eco.extend(sim._eco(x16).tolist())
                time.sleep(len(x) / self.samplerate)

        return Uscita()

    def mic(self, samplerate, channels, dtype, blocksize, device, callback):
        sim = self

        class Mic:
            def __init__(self):
                self._stop = threading.Event()

            def start(self):
                def gira():
                    np = sim.np
                    t0, i = time.monotonic(), 0
                    while not self._stop.is_set():
                        with sim.lock:
                            e = [sim.eco.popleft() for _ in range(min(blocksize, len(sim.eco)))]
                            p, sim.persone = sim.persone[:blocksize], sim.persone[blocksize:]
                        f = sim.rng.normal(0, 3e-4, blocksize).astype(np.float32)
                        f[:len(e)] += np.asarray(e, np.float32)
                        f[:len(p)] += p
                        callback(f.reshape(-1, 1), blocksize, None, None)
                        i += 1
                        attesa = t0 + i * blocksize / 16000 - time.monotonic()
                        if attesa > 0:
                            time.sleep(attesa)
                threading.Thread(target=gira, daemon=True).start()

            def abort(self):
                self._stop.set()

            stop = close = abort

        return Mic()

    def persona(self, frasi16: list, pausa_s: float = 1.2, ritardo_s: float = 1.0):
        np = self.np
        parti = [np.zeros(int(ritardo_s * 16000), np.float32)]
        for x in frasi16:
            parti += [x, np.zeros(int(pausa_s * 16000), np.float32)]
        with self.lock:
            self.persone = np.concatenate(parti)


def voce_16k(nome: str, testi: list[str]) -> list:
    """Le frasi di una persona finta con un'altra voce di Piper, a 16 kHz."""
    import numpy as np
    from piper import PiperVoice
    v = PiperVoice.load(str(RADICE / "voices" / f"{nome}.onnx"))
    out = []
    for t in testi:
        x = np.frombuffer(b"".join(c.audio_int16_bytes for c in v.synthesize(t)),
                          "<i2").astype(np.float32) / 32768
        r = v.config.sample_rate
        n = int(len(x) * 16000 / r)
        out.append((0.5 * np.interp(np.linspace(0, len(x) - 1, n), np.arange(len(x)), x)
                    ).astype(np.float32))
    return out


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass
    o = opzioni(sys.argv[1:])
    scenario = str(o.get("scenario") or "")
    if scenario not in ("muto", "lettura", "chiacchiera"):
        print(__doc__)
        return 2
    import numpy as np
    from calliope.config import load_config
    from calliope.satellite.client import Riproduttore
    from calliope.satellite.stanza import AscoltoStanza
    from calliope.satellite import protocollo as P
    from calliope.stanza import eco as E
    cfg = load_config()
    try:
        from calliope.tts import carica_voce
        voce = carica_voce(cfg, cfg.piper_voice)
    except Exception as e:  # noqa: BLE001
        print(f"Piper non disponibile ({type(e).__name__}: {e}): salto.")
        return SALTA
    try:
        from calliope.stt import make_transcriber
        stt = make_transcriber(cfg)
    except Exception as e:  # noqa: BLE001
        print(f"Whisper non disponibile ({type(e).__name__}: {e}): salto.")
        return SALTA
    from calliope.audio import Listener
    rate = int(getattr(getattr(voce, "config", None), "sample_rate", 22050) or 22050)
    n_frasi = int(o.get("frasi") or len(COPIONE))
    copione = (COPIONE * 3)[:n_frasi]
    senza_voce = bool(o.get("senza_voce"))

    # Le frasi di Calliope: id → (testo, durata, inizio epoch quando comincia a suonare)
    frasi: dict[int, list] = {}

    def suonata(fid, uscita_s):
        if fid in frasi:
            frasi[fid][2] = time.time() + float(uscita_s or 0.0)

    sim = None
    if o.get("a_secco"):
        sim = Simulazione(float(o.get("eco_db") or -30))
    player = Riproduttore(cfg, rate=rate, suonata=suonata,
                          apri_flusso=sim.uscita if sim is not None else None)
    segmenti: dict[int, dict] = {}
    chiusi: list[dict] = []
    lock = threading.Lock()

    def manda(tipo=None, **m):
        with lock:
            if tipo == "stanza_inizio":
                segmenti[m["id"]] = {"pcm": [], "inizio": time.time() - float(m.get("fa_s") or 0)}
            elif tipo == "stanza_fine":
                s = segmenti.pop(m["id"], None)
                if s is not None and m.get("chiusura") in ("silenzio", "pausa_breve", "lunga"):
                    s.update(fine=time.time() - cfg.silence_ms / 1000, durante=m.get(
                        "durante_voce") or [], durata_s=m.get("durata_s"))
                    chiusi.append(s)

    def manda_raw(b):
        _tipo, ident, dati = P.apri_binario(b)
        with lock:
            if ident in segmenti:
                segmenti[ident]["pcm"].append(bytes(dati))
        return True

    stanza = AscoltoStanza(cfg, manda, manda_raw, player.occupato, voce=player.voce_ora,
                           log=print)
    stanza.imposta({"attiva": True, "durante_voce": True})
    lis = Listener(cfg, sorgente=sim.mic if sim is not None else None)
    lis.rubinetto = stanza.frame
    print(f"[MISURA] Scenario «{scenario}», {n_frasi} frasi"
          + (" (Calliope muta: riferimento)" if senza_voce else "") + ".")
    if scenario == "lettura":
        print("\nLeggi ad alta voce, con calma, dall'inizio quando senti la prima frase:\n")
        print(LETTURA + "\n")
    elif scenario == "chiacchiera":
        print("\nChiacchierate liberamente (adulti che lo sanno) mentre Calliope parla.\n")
    else:
        print("\nNessuno parla: si misura solo l'eco.\n")
    if sim is None:
        input("Invio per cominciare… ")
    else:
        try:
            if scenario == "lettura":
                frasi_p = [x for x in LETTURA.replace("! ", ". ").split(". ") if x]
                sim.persona(voce_16k("it_IT-riccardo-medium", frasi_p)
                            if (RADICE / "voices" / "it_IT-riccardo-medium.onnx").is_file()
                            else voce_16k("it_IT-riccardo-x_low", frasi_p), 0.4)
            elif scenario == "chiacchiera":
                a = voce_16k("it_IT-riccardo-x_low", CHIACCHIERA[0::2])
                b = voce_16k("it_IT-paola-medium", CHIACCHIERA[1::2])
                sim.persona([x for c in zip(a, b) for x in c], 0.8)
        except Exception as e:  # noqa: BLE001
            print(f"Voci delle persone finte non disponibili ({e}): salto.")
            return SALTA
    time.sleep(1.0)
    t_inizio = time.time()
    detto_parole = 0
    for k, testo in enumerate(copione, start=1):
        pcm = b"".join(ch.audio_int16_bytes for ch in voce.synthesize(testo))
        frasi[k] = [testo, len(pcm) / 2 / rate, None]
        detto_parole += len(E.parole(testo))
        if senza_voce:
            time.sleep(len(pcm) / 2 / rate + 0.6)
            continue
        player.frase(1, k, testo, rate, len(pcm))
        passo = int(rate * 0.1) * 2
        for i in range(0, len(pcm), passo):
            player.pezzo(k, pcm[i:i + passo])
        while player.occupato(0.0):
            time.sleep(0.05)
        time.sleep(0.6)                  # la pausa fra una risposta e l'altra
    time.sleep(float(cfg.silence_ms) / 1000 + 1.5)
    stanza.imposta({"attiva": False})
    time.sleep(0.5)
    lis.rubinetto = None
    durata_tot = time.time() - t_inizio

    emb = None
    if o.get("campp"):
        try:
            from calliope.speaker_id import SpeakerEmbedder
            emb = SpeakerEmbedder(str(RADICE / "models" / "speaker" /
                                      "3dspeaker_speech_campplus_sv_zh_en_16k-common_advanced.onnx"))
        except Exception as e:  # noqa: BLE001
            print(f"CAM++ non disponibile ({e}): niente similitudini")

    righe, sims = [], []
    grezze_parole = grezze_righe = 0
    for s in chiusi:
        audio = np.frombuffer(b"".join(s["pcm"]), dtype="<i2").astype(np.float32) / 32768
        try:
            testo = stt.transcribe(audio, prompt="")
        except TypeError:
            testo = stt.transcribe(audio)
        testo = (testo or "").strip()
        dette = [E.Detta(frasi[i][0], frasi[i][2], frasi[i][1]) for i in sorted(frasi)
                 if frasi[i][2] is not None
                 and frasi[i][2] - E.TOLLERANZA_S <= s["fine"]
                 and frasi[i][2] + frasi[i][1] + E.CODA_S + E.TOLLERANZA_S >= s["inizio"]]
        if not testo:
            continue
        grezze_righe += 1
        grezze_parole += len(E.parole(testo))
        e = (E.filtra(testo, dette, s["inizio"], s["fine"], nomi=cfg.wake_names)
             if dette else None)
        tenuto = testo if e is None else e.testo
        righe.append({"durante": bool(s["durante"]), "parole": len(E.parole(testo)),
                      "tolte": e.tolte if e else 0, "residua": e.residua if e else 0,
                      "eco": bool(e and e.tutta_eco), "testo": testo, "tenuto": tenuto,
                      "regole": e.regole if e else []})
        if emb is not None and dette and not senza_voce:
            from calliope.speaker_id import normalize
            lei = np.concatenate([np.frombuffer(b"".join(
                ch.audio_int16_bytes for ch in voce.synthesize(d.testo)), "<i2").astype(
                np.float32) / 32768 for d in dette])
            from scipy.signal import resample_poly
            lei = resample_poly(lei, 16000, rate).astype(np.float32)
            sims.append(float(np.dot(emb.embed(audio), normalize(emb.embed(lei)))))

    tenute = [r for r in righe if r["tenuto"]]
    parole_tenute = [w for r in tenute for w, _ in E.parole(r["tenuto"])]
    ris = {"scenario": scenario, "senza_voce": senza_voce, "frasi": n_frasi,
           "parole_dette": detto_parole, "durata_s": round(durata_tot, 1),
           "segmenti": len(chiusi), "durante_voce": sum(bool(s["durante"]) for s in chiusi),
           "righe_grezze": grezze_righe, "parole_grezze": grezze_parole,
           "righe_tenute": len(tenute), "scartate_eco": sum(r["eco"] for r in righe),
           "parole_tolte": sum(r["tolte"] for r in righe)}
    if scenario == "muto":
        ris["righe_false"] = len(tenute)
        ris["eco_residua_100"] = round(100 * len(parole_tenute) / max(1, detto_parole), 2)
        ris["eco_senza_filtro_100"] = round(100 * grezze_parole / max(1, detto_parole), 2)
    else:
        lei = [w for t in copione for w, _ in E.parole(t)]
        if scenario == "lettura":
            letto = [w for w, _ in E.parole(LETTURA)]
            # Le parole tenute che combaciano con lei ma non col testo letto: eco residua
            sm_l = difflib.SequenceMatcher(None, parole_tenute, letto, autojunk=False)
            del_letto = {b.a + k for b in sm_l.get_matching_blocks() for k in range(b.size)}
            resto = [w for i, w in enumerate(parole_tenute) if i not in del_letto]
            sm = difflib.SequenceMatcher(None, resto, lei, autojunk=False)
            ris["eco_residua_100"] = round(100 * sum(b.size for b in sm.get_matching_blocks())
                                           / max(1, detto_parole), 2)
            ris["wer_lettura"] = round(wer(letto, parole_tenute), 3)
            ris["parole_lette"] = len(letto)
        else:
            ris["eco_residua_stimata_100"] = round(
                100 * sum(r["residua"] for r in righe) / max(1, detto_parole), 2)
    if sims:
        v = sorted(sims)
        ris["campp"] = {"n": len(v), "min": round(v[0], 3), "p50": round(v[len(v) // 2], 3),
                        "max": round(v[-1], 3)}
    print("\n[MISURA] " + json.dumps(ris, ensure_ascii=False, indent=1))
    if o.get("testi"):
        for r in righe:
            print(f"  {'eco ' if r['eco'] else 'riga'} {r['testo']!r} → {r['tenuto']!r} "
                  f"{r['regole']}")
    if o.get("salva"):
        d = Path(str(o["salva"]))
        d.mkdir(parents=True, exist_ok=True)
        nome = datetime.datetime.now().strftime("misura-%Y%m%d-%H%M") + f"-{scenario}"
        if o.get("testi"):
            ris["righe"] = righe
        (d / f"{nome}.json").write_text(json.dumps(ris, ensure_ascii=False, indent=1),
                                       encoding="utf-8")
        if o.get("audio"):
            for k, s in enumerate(chiusi):
                with wave.open(str(d / f"{nome}-{k:03d}.wav"), "wb") as w:
                    w.setnchannels(1)
                    w.setsampwidth(2)
                    w.setframerate(cfg.sample_rate)
                    w.writeframes(b"".join(s["pcm"]))
        print(f"[MISURA] salvato in {d}")
    try:
        lis.stream.stop()
        lis.stream.close()
    except Exception:  # noqa: BLE001
        pass
    sys.stdout.flush()
    os._exit(0)


if __name__ == "__main__":
    sys.exit(main())
