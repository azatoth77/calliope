r"""Motori di cancellazione dell'eco (AEC) provati per il «livello B» del barge-in.

Ogni motore prende il segnale del microfono (near-end, con l'eco) e il riferimento
(far-end, ciò che Calliope sta riproducendo, già a 16 kHz sulla linea temporale del
microfono) e restituisce il microfono ripulito. Tutti lavorano a blocchi, come
farebbero in tempo reale; qui si chiamano su file interi solo per comodità.

Va usato con il venv separato aec\.venv (livekit, pyaec, ai-edge-litert).
"""
import ctypes
import time
from pathlib import Path

import numpy as np

SR = 16000
BLOCK = 160                     # 10 ms: blocco di AEC3 e di speexdsp qui
DTLN_DIR = Path(__file__).resolve().parent / "modelli" / "dtln"


def to_i16(x: np.ndarray) -> np.ndarray:
    return np.clip(np.round(x * 32768), -32768, 32767).astype(np.int16)


def stima_ritardo(mic: np.ndarray, ref: np.ndarray, max_s: float = 1.0) -> int:
    """Ritardo dell'eco rispetto al riferimento (campioni), con GCC-PHAT."""
    n = len(mic)
    X = np.fft.rfft(mic, 2 * n) * np.conj(np.fft.rfft(ref, 2 * n))
    cc = np.fft.irfft(X / (np.abs(X) + 1e-12))
    return int(np.argmax(cc[: int(max_s * SR)]))


def ritarda(ref: np.ndarray, d: int) -> np.ndarray:
    if d <= 0:
        return ref
    return np.concatenate([np.zeros(d, ref.dtype), ref])[: len(ref)]


class Motore:
    nome = "?"
    allinea = False              # se True il riferimento si ritarda della stima GCC-PHAT
    margine_ms = 30              # ...meno un margine: il filtro deve restare causale
    stima_s = 20.0               # secondi usati per la stima (all'inizio del flusso)

    def run(self, mic: np.ndarray, ref: np.ndarray) -> tuple[np.ndarray, float]:
        """Restituisce (uscita, ms di CPU per 10 ms di audio)."""
        if self.allinea:
            n = min(len(mic), int(self.stima_s * SR))
            self.ritardo = stima_ritardo(mic[:n], ref[:n])
            ref = ritarda(ref, self.ritardo - int(self.margine_ms * SR / 1000))
        t = time.perf_counter()
        out = self._run(mic.astype(np.float32), ref.astype(np.float32))
        cpu = (time.perf_counter() - t) * 1000 / (len(mic) / BLOCK)
        return out[: len(mic)], cpu

    def _run(self, mic, ref):
        raise NotImplementedError


class Nessuna(Motore):
    nome = "nessuna"

    def _run(self, mic, ref):
        return mic.copy()


class Speex(Motore):
    """speexdsp (MDF + preprocessore con soppressione dell'eco residua) via pyaec."""

    def __init__(self, filtro_ms=512, allinea=False, preprocess=True):
        self.filtro = int(filtro_ms * SR / 1000)
        self.allinea, self.preprocess = allinea, preprocess
        self.nome = f"speex{'+allin' if allinea else ''}"

    def _run(self, mic, ref):
        import pyaec
        lib, P = pyaec.lib, ctypes.POINTER(ctypes.c_int16)
        a = pyaec.Aec(BLOCK, self.filtro, SR, self.preprocess)
        m, r = to_i16(mic), to_i16(ref)
        n = len(m) // BLOCK * BLOCK
        out = np.zeros(len(m), np.int16)
        for i in range(0, n, BLOCK):
            mb, rb = np.ascontiguousarray(m[i:i + BLOCK]), np.ascontiguousarray(r[i:i + BLOCK])
            ob = np.zeros(BLOCK, np.int16)
            lib.AecCancelEcho(a._aec, mb.ctypes.data_as(P), rb.ctypes.data_as(P),
                              ob.ctypes.data_as(P), BLOCK)
            out[i:i + BLOCK] = ob
        return out.astype(np.float32) / 32768


class AEC3(Motore):
    """WebRTC AEC3 tramite livekit.rtc.AudioProcessingModule (libwebrtc in Rust/FFI)."""

    def __init__(self, ns=False, hint_ms=None, allinea=False, hpf=True):
        self.ns, self.hint_ms, self.allinea, self.hpf = ns, hint_ms, allinea, hpf
        self.nome = "aec3" + ("+ns" if ns else "") + ("+allin" if allinea else "") + \
            (f"+hint{hint_ms}" if hint_ms is not None else "")

    def _run(self, mic, ref):
        from livekit import rtc
        apm = rtc.AudioProcessingModule(echo_cancellation=True, noise_suppression=self.ns,
                                        high_pass_filter=self.hpf, auto_gain_control=False)
        m, r = to_i16(mic), to_i16(ref)
        n = len(m) // BLOCK * BLOCK
        out = np.zeros(len(m), np.int16)
        for i in range(0, n, BLOCK):
            if self.hint_ms is not None:
                apm.set_stream_delay_ms(self.hint_ms)
            apm.process_reverse_stream(rtc.AudioFrame(r[i:i + BLOCK].tobytes(), SR, 1, BLOCK))
            f = rtc.AudioFrame(m[i:i + BLOCK].tobytes(), SR, 1, BLOCK)
            apm.process_stream(f)
            out[i:i + BLOCK] = np.frombuffer(f.data, np.int16)
        return out.astype(np.float32) / 32768


class DTLN(Motore):
    """DTLN-aec (Westhausen, MIT), modelli TF-Lite ufficiali eseguiti con LiteRT.

    Finestra 32 ms, passo 8 ms: latenza algoritmica 24 ms.
    """

    def __init__(self, size=256, allinea=False):
        self.size, self.allinea = size, allinea
        self.nome = f"dtln{size}" + ("+allin" if allinea else "")

    def _run(self, mic, ref):
        from ai_edge_litert.interpreter import Interpreter
        base = DTLN_DIR / f"dtln_aec_{self.size}"
        i1 = Interpreter(model_path=f"{base}_1.tflite", num_threads=1)
        i2 = Interpreter(model_path=f"{base}_2.tflite", num_threads=1)
        i1.allocate_tensors()
        i2.allocate_tensors()
        in1, out1 = i1.get_input_details(), i1.get_output_details()
        in2, out2 = i2.get_input_details(), i2.get_output_details()
        st1 = np.zeros(in1[1]["shape"], np.float32)
        st2 = np.zeros(in2[1]["shape"], np.float32)
        L, S = 512, 128
        pad = np.zeros(L - S, np.float32)
        a = np.concatenate([pad, mic, pad])
        b = np.concatenate([pad, ref, pad])
        out = np.zeros(len(a), np.float32)
        ib, ibl, ob = np.zeros(L, np.float32), np.zeros(L, np.float32), np.zeros(L, np.float32)
        for k in range((len(a) - (L - S)) // S):
            ib[:-S] = ib[S:]
            ib[-S:] = a[k * S:k * S + S]
            ibl[:-S] = ibl[S:]
            ibl[-S:] = b[k * S:k * S + S]
            F = np.fft.rfft(ib).astype(np.complex64)
            Fl = np.abs(np.fft.rfft(ibl)).astype(np.float32).reshape(1, 1, -1)
            i1.set_tensor(in1[0]["index"], np.abs(F).astype(np.float32).reshape(1, 1, -1))
            i1.set_tensor(in1[2]["index"], Fl)
            i1.set_tensor(in1[1]["index"], st1)
            i1.invoke()
            mask = i1.get_tensor(out1[0]["index"])
            st1 = i1.get_tensor(out1[1]["index"])
            est = np.fft.irfft(F * mask).astype(np.float32).reshape(1, 1, -1)
            i2.set_tensor(in2[1]["index"], st2)
            i2.set_tensor(in2[0]["index"], est)
            i2.set_tensor(in2[2]["index"], ibl.reshape(1, 1, -1))
            i2.invoke()
            blk = i2.get_tensor(out2[0]["index"])
            st2 = i2.get_tensor(out2[1]["index"])
            ob[:-S] = ob[S:]
            ob[-S:] = 0
            ob += np.squeeze(blk)
            out[k * S:k * S + S] = ob[:S]
        return out[L - S:L - S + len(mic)]


def tutti():
    """I motori confrontati nel rapporto."""
    return [
        Nessuna(),
        Speex(filtro_ms=512),
        Speex(filtro_ms=200, allinea=True),
        AEC3(),
        AEC3(ns=True),
        AEC3(allinea=True),
        DTLN(128),
        DTLN(256),
        DTLN(512),
        DTLN(128, allinea=True),
        DTLN(256, allinea=True),
        DTLN(512, allinea=True),
    ]
