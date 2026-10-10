"""
Misura: quanto costa a Calliope parlare Wyoming senza dipendenze (10/10/2026, rapporto
docs/ricerche/2026-10-10-wyoming.md). Manuale, non nel runner.

    python -m venv %TEMP%\\wy && %TEMP%\\wy\\Scripts\\pip install wyoming==1.10.2
    %TEMP%\\wy\\Scripts\\python prove\\misura_wyoming.py [--giri 3]

Due lati nello stesso processo, sulla stessa macchina (127.0.0.1):

- **satellite finto** scritto con la libreria ufficiale `wyoming` (il ruolo di
  `wyoming-satellite`): server TCP, risponde a describe, aspetta run-satellite, poi fa come dopo
  una wake word locale (detection, run-pipeline asr → tts, audio-start) e manda il microfono in
  tempo reale a pezzi da 1024 campioni: 2 s di «voce» (un tono), poi silenzio finché non arriva
  transcript. Riceve la risposta (audio-start/chunk/stop) e risponde played;
- **lato Calliope** scritto a mano, solo libreria standard, socket sincroni (il ruolo che oggi
  ha Home Assistant): si collega, describe, run-satellite, riceve l'audio, chiude la frase dopo
  0,3 s sotto una soglia d'energia (al posto del VAD), manda transcript e poi la risposta frase
  per frase (tre frasi da 1,2 s a 22 050 Hz, la prima «pronta» dopo 0,25 s e le altre ogni
  0,35 s: ritardi finti di modello e Piper), audio-stop alla fine.

Stampa per ogni giro: dalla fine della voce al transcript e al primo pezzo di risposta visti dal
satellite, la risposta (pezzi, byte, formato), il costo dell'inquadramento (intestazioni JSON
sui byte di audio) e gli eventi visti. Senza `wyoming` installato esce con 77.
"""
import argparse
import asyncio
import json
import math
import socket
import struct
import sys
import threading
import time

RATE_MIC, PEZZO_MIC = 16000, 1024
RATE_TTS, PEZZO_TTS = 22050, 1024
RITARDI_FRASE = (0.25, 0.35, 0.35)
DURATA_FRASE = 1.2
SILENZIO_FINE = 0.3


def tono(n: int, rate: int, freq: float, ampiezza: int, t0: int = 0) -> bytes:
    return b"".join(struct.pack("<h", int(ampiezza * math.sin(2 * math.pi * freq * (t0 + i) / rate)))
                    for i in range(n))


# ---------------------------------------------------------------- lato Calliope, a mano

class Wyoming:
    """Inquadramento di Wyoming: una riga JSON (type, data_length, payload_length), poi i dati
    in più (JSON) e il payload (PCM)."""

    def __init__(self, sock: socket.socket):
        self.sock = sock
        self.f = sock.makefile("rb")
        self.byte_intestazioni = 0
        self.byte_payload = 0

    def scrivi(self, tipo: str, data: dict | None = None, payload: bytes | None = None):
        testa = {"type": tipo, "version": "1.10.2"}
        corpo = json.dumps(data, ensure_ascii=False).encode() if data else b""
        if corpo:
            testa["data_length"] = len(corpo)
        if payload:
            testa["payload_length"] = len(payload)
        riga = json.dumps(testa).encode() + b"\n"
        self.byte_intestazioni += len(riga) + len(corpo)
        self.byte_payload += len(payload or b"")
        self.sock.sendall(riga + corpo + (payload or b""))

    def leggi(self):
        riga = self.f.readline()
        if not riga:
            return None
        testa = json.loads(riga)
        data = testa.get("data") or {}
        if testa.get("data_length"):
            data.update(json.loads(self.f.read(testa["data_length"])))
        payload = self.f.read(testa["payload_length"]) if testa.get("payload_length") else b""
        return testa["type"], data, payload


def rms(pcm: bytes) -> float:
    n = len(pcm) // 2
    v = struct.unpack(f"<{n}h", pcm[: n * 2]) if n else ()
    return math.sqrt(sum(x * x for x in v) / n) if n else 0.0


def lato_calliope(porta: int) -> dict:
    s = socket.create_connection(("127.0.0.1", porta))
    s.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
    w = Wyoming(s)
    w.scrivi("describe")
    tipo, info, _ = w.leggi()
    assert tipo == "info", tipo
    w.scrivi("run-satellite")
    eventi, silenzio, sentita = set(), 0.0, False
    while True:
        tipo, data, payload = w.leggi()
        eventi.add(tipo)
        if tipo != "audio-chunk":
            continue
        if rms(payload) > 500:
            sentita, silenzio = True, 0.0
        elif sentita:
            silenzio += len(payload) / 2 / data["rate"]
            if silenzio >= SILENZIO_FINE:
                break
    # Qui Calliope avrebbe la frase intera: Whisper e CAM++ sullo stesso PCM
    w.scrivi("transcript", {"text": "che ore sono"})
    w.scrivi("audio-start", {"rate": RATE_TTS, "width": 2, "channels": 1, "timestamp": 0})
    ms = 0
    for ritardo in RITARDI_FRASE:
        time.sleep(ritardo)
        pcm = tono(int(DURATA_FRASE * RATE_TTS), RATE_TTS, 220, 6000)
        for k in range(0, len(pcm), PEZZO_TTS * 2):
            pezzo = pcm[k:k + PEZZO_TTS * 2]
            w.scrivi("audio-chunk", {"rate": RATE_TTS, "width": 2, "channels": 1, "timestamp": ms}, pezzo)
            ms += len(pezzo) * 1000 // (2 * RATE_TTS)
    w.scrivi("audio-stop", {"timestamp": ms})
    while (ev := w.leggi()) is not None:
        eventi.add(ev[0])
        if ev[0] == "played":
            break
    s.close()
    return {"programmi_in_info": sorted(info), "eventi_dal_satellite": sorted(eventi),
            "costo_inquadramento_pct": round(100 * w.byte_intestazioni / max(1, w.byte_payload), 2)}


# ---------------------------------------------------------------- satellite, libreria ufficiale

async def satellite(porta: int, pronto: threading.Event, misure: dict):
    from wyoming.asr import Transcript
    from wyoming.audio import AudioChunk, AudioStart, AudioStop
    from wyoming.event import async_read_event, async_write_event
    from wyoming.info import Attribution, Describe, Info, Satellite
    from wyoming.pipeline import PipelineStage, RunPipeline
    from wyoming.satellite import RunSatellite
    from wyoming.snd import Played
    from wyoming.wake import Detection

    fatto = asyncio.Event()

    async def cliente(reader, writer):
        while True:
            ev = await async_read_event(reader)
            if Describe.is_type(ev.type):
                sat = Satellite(name="finto", attribution=Attribution("prova", ""), installed=True,
                                description="satellite finto", version="0", area="studio")
                await async_write_event(Info(satellite=sat).event(), writer)
            elif RunSatellite.is_type(ev.type):
                break
        await async_write_event(Detection(name="ok_nabu").event(), writer)
        await async_write_event(RunPipeline(start_stage=PipelineStage.ASR,
                                            end_stage=PipelineStage.TTS).event(), writer)
        await async_write_event(AudioStart(rate=RATE_MIC, width=2, channels=1).event(), writer)
        stop = asyncio.Event()
        stato = {"fine_voce": None}

        async def microfono():
            t, inizio = 0, time.perf_counter()
            while not stop.is_set():
                parla = t < 2 * RATE_MIC
                pcm = tono(PEZZO_MIC, RATE_MIC, 440, 8000, t) if parla else b"\0" * (PEZZO_MIC * 2)
                await async_write_event(AudioChunk(rate=RATE_MIC, width=2, channels=1, audio=pcm).event(), writer)
                t += PEZZO_MIC
                if not parla and stato["fine_voce"] is None:
                    stato["fine_voce"] = time.perf_counter()
                attesa = inizio + t / RATE_MIC - time.perf_counter()
                if attesa > 0:
                    await asyncio.sleep(attesa)
            await async_write_event(AudioStop().event(), writer)

        mic = asyncio.create_task(microfono())
        pezzi, t_transcript, t_start, formato = [], None, None, None
        while (ev := await async_read_event(reader)) is not None:
            ora = time.perf_counter()
            if Transcript.is_type(ev.type):
                t_transcript = ora
                stop.set()
            elif AudioStart.is_type(ev.type):
                a = AudioStart.from_event(ev)
                t_start, formato = ora, [a.rate, a.width, a.channels]
            elif AudioChunk.is_type(ev.type):
                pezzi.append((ora, len(ev.payload or b"")))
            elif AudioStop.is_type(ev.type):
                await async_write_event(Played().event(), writer)
                misure.update({
                    "fine_voce_a_transcript_s": round(t_transcript - stato["fine_voce"], 3),
                    "fine_voce_a_primo_audio_s": round(pezzi[0][0] - stato["fine_voce"], 3),
                    "pezzi_risposta": len(pezzi), "byte_risposta": sum(n for _, n in pezzi),
                    "formato_risposta": formato, "invio_risposta_s": round(ora - t_start, 3)})
                break
        await mic
        writer.close()
        fatto.set()

    server = await asyncio.start_server(cliente, "127.0.0.1", porta)
    pronto.set()
    await fatto.wait()
    server.close()


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    ap.add_argument("--giri", type=int, default=3)
    ap.add_argument("--porta", type=int, default=10791)
    a = ap.parse_args()
    try:
        import wyoming  # noqa: F401
    except ImportError:
        print("Serve la libreria wyoming (pip install wyoming==1.10.2) in un venv a parte.")
        sys.exit(77)
    for giro in range(1, a.giri + 1):
        misure, pronto = {}, threading.Event()
        th = threading.Thread(target=lambda: asyncio.run(satellite(a.porta, pronto, misure)))
        th.start()
        pronto.wait(10)
        misure.update(lato_calliope(a.porta))
        th.join(30)
        print(json.dumps({"giro": giro, **misure}, ensure_ascii=False))


if __name__ == "__main__":
    main()
