import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

"""Prova a secco del G.711 μ-law vero e della conversione dei file di prima (14/10/2026 sera,
calliope/conserva.py: `mulaw`, `da_mulaw`, `wav_mulaw`, `formato_wav`, `leggi_wav`,
`converti_file`, `converti_audio`, `python -m calliope.conserva --converti-audio`).

Il difetto: fino al 14/10 `mulaw` quantizzava in modo lineare la curva continua di μ-law e la
complementava, ma il WAV diceva «formato 7» (G.711): Calliope si rileggeva giusto, ogni lettore
standard sentiva rumore. Qui:

- il codificatore uguale, su tutti i 65 536 valori a 16 bit, a un codificatore di riferimento
  scritto qui (il g711.c classico, un campione alla volta con i segmenti); il decodificatore
  uguale, su tutti i 256 byte, alla formula del G.711 scritta in un altro modo, e i valori noti
  (0xFF e 0x7F → 0, 0x80 → +32124, 0x00 → -32124);
- un lettore standard: un parser dei chunk RIFF scritto qui con la decodifica di riferimento, e
  libsndfile (`soundfile`) se c'è, rileggono l'onda con un SNR alto (un tono, la voce di Piper
  dei campioni in voices/campioni se ci sono); il contrario: il formato di prima letto da un
  lettore standard è storto (SNR basso);
- il segno del formato (LIST/INFO/ISFT «Calliope G.711»): `formato_wav` distingue nuovo,
  vecchio, PCM e altro; `leggi_wav` legge giusto sia il nuovo sia il vecchio;
- la conversione: voce conservata, banco della stanza e audio degli avvisi nel cassetto
  convertiti (permessi 600 e data del file tenuti, dimensione nel cassetto aggiornata, il .json
  del banco intatto); contrari: i file già nuovi, un PCM, un file rotto e un audio μ-law di una
  persona nel cassetto (non un avviso) non si toccano; rilanciata non cambia niente
  (idempotente); interrotta a metà lascia i file vecchi interi e niente temporanei, un
  temporaneo lasciato da un crollo si toglie, e il rilancio finisce il lavoro; un file tolto
  nel frattempo è «sparito»; da terminale solo conteggi, mai nomi né percorsi.

Nomi di fantasia. Tutto in una cartella temporanea. ~2 s.
"""

import contextlib
import io
import shutil
import sqlite3
import struct
import tempfile
import time
from pathlib import Path
from types import SimpleNamespace

import numpy as np

from calliope import conserva as C

errori = 0
RADICE = Path(__file__).resolve().parent.parent


def verifica(nome, ok, dettaglio=""):
    global errori
    print(("OK  " if ok else "ERR ") + nome + ("" if ok else f"  → {dettaglio}"))
    if not ok:
        errori += 1


def snr(a, b) -> float:
    n = min(len(a), len(b))
    a, b = np.asarray(a[:n], dtype=np.float64), np.asarray(b[:n], dtype=np.float64)
    return float(10 * np.log10(np.sum(a ** 2) / max(np.sum((a - b) ** 2), 1e-20)))


# ───────── riferimenti indipendenti (scritti qui, un campione alla volta) ─────────
def rif_codifica(pcm: int) -> int:
    """linear2ulaw del g711.c classico (16 bit, BIAS 0x84, tetto 32635)."""
    if pcm < 0:
        pcm, mask = -pcm, 0x7F
    else:
        mask = 0xFF
    pcm = min(pcm, 32635) + 0x84
    for seg, fine in enumerate((0xFF, 0x1FF, 0x3FF, 0x7FF, 0xFFF, 0x1FFF, 0x3FFF, 0x7FFF)):
        if pcm <= fine:
            return ((seg << 4) | ((pcm >> (seg + 3)) & 0x0F)) ^ mask
    return 0x7F ^ mask


def rif_decodifica(byte: int) -> int:
    """G.711: il byte complementato è segno (1 bit), esponente (3) e mantissa (4); il modulo,
    in unità di 14 bit, è ((2·mantissa + 33) << esponente) - 33; a 16 bit per 4."""
    u = (~byte) & 0xFF
    segno, esp, mant = u >> 7, (u >> 4) & 0x07, u & 0x0F
    modulo = 4 * (((2 * mant + 33) << esp) - 33)
    return -modulo if segno else modulo


def lettore_standard(b: bytes):
    """Un lettore di WAV come quelli di fuori: chunk RIFF, formato 7 → G.711 di riferimento.
    Ignora i chunk che non conosce (LIST compreso)."""
    assert b[:4] == b"RIFF" and b[8:12] == b"WAVE"
    i, fmt, sr, dati = 12, None, None, None
    while i + 8 <= len(b):
        nome, n = b[i:i + 4], struct.unpack("<I", b[i + 4:i + 8])[0]
        if nome == b"fmt ":
            fmt, _ch, sr = struct.unpack("<HHI", b[i + 8:i + 16])
        elif nome == b"data":
            dati = b[i + 8:i + 8 + n]
        i += 8 + n + (n % 2)
    assert fmt == 7, fmt
    tab = np.array([rif_decodifica(k) for k in range(256)], dtype=np.float32) / 32768.0
    return tab[np.frombuffer(dati, dtype=np.uint8)], sr


def wav_vecchio(audio, sr=16000) -> bytes:
    """Il WAV come lo scriveva Calliope fino al 14/10 (copia del codice di allora)."""
    x = np.clip(np.asarray(audio, dtype=np.float32), -1.0, 1.0)
    y = np.sign(x) * np.log1p(255.0 * np.abs(x)) / np.log1p(255.0)
    q = np.clip(np.round((y + 1.0) / 2.0 * 255.0).astype(np.int16), 0, 255).astype(np.uint8)
    dati = (~q).astype(np.uint8).tobytes()
    n = len(dati)
    fmt = struct.pack("<HHIIHHH", 7, 1, int(sr), int(sr), 1, 8, 0)
    pad = b"\x00" if n % 2 else b""
    corpo = (b"WAVE" + b"fmt " + struct.pack("<I", len(fmt)) + fmt
             + b"fact" + struct.pack("<II", 4, n) + b"data" + struct.pack("<I", n) + dati + pad)
    return b"RIFF" + struct.pack("<I", len(corpo)) + corpo


def wav_pcm16(audio, sr=16000) -> bytes:
    dati = (np.clip(audio, -1, 1) * 32767).astype("<i2").tobytes()
    fmt = struct.pack("<HHIIHH", 1, 1, sr, sr * 2, 2, 16)
    corpo = b"WAVE" + b"fmt " + struct.pack("<I", 16) + fmt + b"data" + struct.pack(
        "<I", len(dati)) + dati
    return b"RIFF" + struct.pack("<I", len(corpo)) + corpo


SR = 16000
tt = np.arange(SR) / SR
TONO = (0.3 * np.sin(2 * np.pi * 440 * tt) + 0.05 * np.sin(2 * np.pi * 1700 * tt)).astype(
    np.float32)


def voce_piper():
    """Un campione della voce di Piper (voices/campioni, fuori da git) a 16 kHz, o None."""
    cart = RADICE / "voices" / "campioni"
    for nome in ("it_IT-paola-medium.wav", "it_IT-aurora-medium.wav"):
        p = cart / nome
        if p.exists():
            try:
                a, sr = C.leggi_wav(p)
            except Exception:  # noqa: BLE001
                continue
            n = int(len(a) * SR / sr)
            return np.interp(np.linspace(0, len(a) - 1, n), np.arange(len(a)), a).astype(
                np.float32)
    return None


# ───────── il codec ─────────
tutti = np.arange(-32768, 32768, dtype=np.int32).astype(np.int16)
rif = bytes(rif_codifica(int(v)) for v in tutti)
mio = C.mulaw(tutti)
verifica("codifica uguale al riferimento su tutti i 65 536 valori a 16 bit", rif == mio,
         sum(a != b for a, b in zip(rif, mio)))
dec = C.da_mulaw(bytes(range(256))) * 32768.0
rif_dec = np.array([rif_decodifica(k) for k in range(256)], dtype=np.float32)
verifica("decodifica uguale alla formula del G.711 su tutti i 256 byte",
         np.array_equal(dec, rif_dec), np.nonzero(dec != rif_dec))
verifica("valori noti: 0xFF e 0x7F → 0, 0x80 → +32124, 0x00 → -32124, 0xFE → +8",
         list(C.da_mulaw(bytes([0xFF, 0x7F, 0x80, 0x00, 0xFE])) * 32768) == [0, 0, 32124,
                                                                             -32124, 8])
verifica("lo zero è 0xFF, il massimo 0x80, il minimo 0x00",
         C.mulaw([0.0]) == b"\xff" and C.mulaw([1.0]) == b"\x80" and C.mulaw([-1.0]) == b"\x00",
         C.mulaw([0.0, 1.0, -1.0]))
codici = bytes(k for k in range(256) if k != 0x7F)           # 0x7F è lo zero negativo
verifica("ricodificare i valori decodificati ridà gli stessi byte",
         C.mulaw(C.da_mulaw(codici)) == codici)
verifica("float32 e int16 danno gli stessi byte",
         C.mulaw(np.round(TONO * 32768).astype(np.int16)) == C.mulaw(
             np.round(TONO * 32768).astype(np.float32) / 32768.0))
verifica("vuoto → vuoto", C.mulaw(np.zeros(0, dtype=np.float32)) == b""
         and len(C.da_mulaw(b"")) == 0)

# ───────── un lettore standard ─────────
b_nuovo = C.wav_mulaw(TONO, SR)
letto, sr_l = lettore_standard(b_nuovo)
s_tono = snr(TONO, letto)
verifica(f"tono: il lettore standard rilegge l'onda (SNR {s_tono:.1f} dB > 35)",
         sr_l == SR and len(letto) == len(TONO) and s_tono > 35, s_tono)
s_vecchio = snr(TONO, lettore_standard(wav_vecchio(TONO))[0])
verifica(f"contrario: il formato di prima letto da un lettore standard è storto "
         f"(SNR {s_vecchio:.1f} dB < 10)", s_vecchio < 10, s_vecchio)
voce = voce_piper()
if voce is None:
    print("SALTATA IN PARTE: la voce di Piper (voices/campioni assente)")
else:
    s_voce = snr(voce, lettore_standard(C.wav_mulaw(voce, SR))[0])
    verifica(f"voce di Piper: il lettore standard la rilegge (SNR {s_voce:.1f} dB > 30)",
             s_voce > 30, s_voce)
try:
    import soundfile as sf
except ImportError:
    sf = None
    print("SALTATA IN PARTE: libsndfile (soundfile non installato)")
if sf is not None:
    y, sr_sf = sf.read(io.BytesIO(b_nuovo), dtype="float32")
    verifica("libsndfile legge il WAV nuovo uguale a da_mulaw e al riferimento",
             sr_sf == SR and np.array_equal(y, letto) and np.array_equal(y, C.da_mulaw(
                 C.mulaw(TONO))), snr(TONO, y))
    info = sf.info(io.BytesIO(b_nuovo))
    verifica("libsndfile lo riconosce come μ-law", "U-Law" in info.subtype_info
             or "ULAW" in info.subtype, info.subtype)
    s_sf_v = snr(TONO, sf.read(io.BytesIO(wav_vecchio(TONO)), dtype="float32")[0])
    verifica("contrario: libsndfile sul formato di prima è storto", s_sf_v < 10, s_sf_v)

# ───────── il segno del formato ─────────
verifica("formato: nuovo «g711», di prima «vecchio», PCM «pcm16», rotto «altro»",
         [C.formato_wav(x) for x in (b_nuovo, wav_vecchio(TONO), wav_pcm16(TONO), b"RIFF1234",
                                     b"")] == ["g711", "vecchio", "pcm16", "altro", "altro"])
verifica("il segno sta prima dei dati (basta l'intestazione)",
         C.formato_wav(b_nuovo[:200]) == "g711")
tmp = Path(tempfile.mkdtemp(prefix="prova_mulaw_"))
try:
    (tmp / "n.wav").write_bytes(b_nuovo)
    (tmp / "v.wav").write_bytes(wav_vecchio(TONO))
    a_n, _ = C.leggi_wav(tmp / "n.wav")
    a_v, _ = C.leggi_wav(tmp / "v.wav")
    verifica("leggi_wav: il nuovo con il G.711", snr(TONO, a_n) > 35, snr(TONO, a_n))
    verifica("leggi_wav: il vecchio con la decodifica di allora", snr(TONO, a_v) > 30,
             snr(TONO, a_v))
    # avvisi_audio.wav: lo stesso formato, col segno
    from calliope import avvisi_audio as AA
    pz = AA.Pezzo("stanza:s1", "p-min", True, 0.0, 1.0, C.mulaw(TONO))
    b_av = AA.wav([pz, pz], pausa_s=0.1)
    l_av, _ = lettore_standard(b_av)
    verifica("audio degli avvisi: G.711 col segno, il lettore standard lo rilegge",
             C.formato_wav(b_av) == "g711" and len(l_av) == 2 * SR + 1600
             and snr(TONO, l_av[:SR]) > 35 and not np.any(l_av[SR:SR + 1600]))

    # ───────── la conversione ─────────
    reg = tmp / "registro"
    vecchio_a = wav_vecchio(TONO)
    voce_v = reg / "voce" / "p-adu" / "2026-10-10" / "101010.wav"
    voce_n = reg / "voce" / "p-adu" / "2026-10-10" / "111111.wav"
    voce_pcm = reg / "voce" / "p-adu" / "2026-10-11" / "1.wav"
    voce_rotto = reg / "voce" / "p-adu" / "2026-10-11" / "2.wav"
    banco_v = reg / "stanza_banco" / "sat1" / "2026-10-14" / "201010-seg1.wav"
    banco_j = banco_v.with_suffix(".json")
    for p, b in ((voce_v, vecchio_a), (voce_n, b_nuovo), (voce_pcm, wav_pcm16(TONO)),
                 (voce_rotto, b"RIFF\x10\x00\x00\x00WAVEfmt "), (banco_v, vecchio_a),
                 (banco_j, b'{"persone": ["p-adu"]}')):
        C._scrivi_privato(p, b)
    vecchia_data = time.time() - 5 * 86400
    for p in (voce_v, banco_v):
        os.utime(p, (vecchia_data, vecchia_data))
    # Il cassetto: un avviso con l'audio di prima, e un audio μ-law mandato da una persona
    from calliope.cassetto import Cassetto
    db = tmp / "memoria.db"
    cas = Cassetto(str(db), log=lambda m: None)
    fid_av = cas.metti("p-tut", vecchio_a, "Avviso Bianca.wav", "audio", fonte="avviso")
    fid_al = cas.metti("p-tut", vecchio_a, "registrazione.wav", "audio", fonte="telefono")
    p_av = cas._percorso(cas._riga(fid_av))
    p_al = cas._percorso(cas._riga(fid_al))
    cas.close()
    cfg = SimpleNamespace(turn_log_dir=str(reg), memory_db=str(db), cassetto_cartella="")
    prima = {p: p.read_bytes() for p in (voce_n, voce_pcm, voce_rotto, banco_j, p_al)}

    log = []
    r = C.converti_audio(cfg, log=log.append)
    verifica("conversione: 3 file (voce 1, banco 1, avvisi 1), 1 già nuovo, 2 d'altro formato",
             (r["convertiti"], r["voce"], r["banco"], r["avvisi"], r["gia_nuovi"], r["altri"],
              r["errori"]) == (3, 1, 1, 1, 1, 2, 0), r)
    for nome, p in (("voce", voce_v), ("banco", banco_v), ("avviso", p_av)):
        b = p.read_bytes()
        verifica(f"{nome}: ora G.711 col segno, il lettore standard rilegge l'onda",
                 C.formato_wav(b) == "g711" and snr(TONO, lettore_standard(b)[0]) > 28,
                 (C.formato_wav(b), snr(TONO, lettore_standard(b)[0])))
    verifica("la data del file è tenuta (la rotazione del banco la guarda)",
             abs(voce_v.stat().st_mtime - vecchia_data) < 2
             and abs(banco_v.stat().st_mtime - vecchia_data) < 2)
    if os.name == "posix":
        modi = {oct(p.stat().st_mode & 0o777) for p in (voce_v, banco_v, p_av)}
        verifica("permessi 600 tenuti", modi == {"0o600"}, modi)
    else:
        print("OK  permessi 600 (su Windows non si guardano)")
    verifica("contrari non toccati: il già nuovo, il PCM, il rotto, il .json del banco, "
             "l'audio di una persona nel cassetto",
             all(p.read_bytes() == b for p, b in prima.items()))
    con = sqlite3.connect(db)
    dim = dict(con.execute("SELECT id, dimensione FROM cassetto_file").fetchall())
    con.close()
    verifica("cassetto: la dimensione dell'avviso aggiornata, quella dell'altro no",
             dim[fid_av] == p_av.stat().st_size and dim[fid_al] == len(vecchio_a), dim)
    verifica("niente temporanei lasciati", not list(tmp.rglob("*" + C.TEMPORANEO_CONV)))
    verifica("nel log niente nomi né percorsi", not any("p-adu" in m or str(tmp) in m
                                                         for m in log), log)
    dopo = {p: p.read_bytes() for p in reg.rglob("*") if p.is_file()}
    dopo[p_av] = p_av.read_bytes()
    r2 = C.converti_audio(cfg, log=log.append)
    verifica("rilanciata: niente da convertire, 4 già nuovi, file identici (idempotente)",
             r2["convertiti"] == 0 and r2["gia_nuovi"] == 4
             and all(p.read_bytes() == b for p, b in dopo.items()), r2)

    # ───────── interrotta a metà ─────────
    giro = reg / "voce" / "p-giro" / "2026-10-12"
    vecchi = [giro / f"{k}.wav" for k in range(5)]
    for p in vecchi:
        C._scrivi_privato(p, vecchio_a)
    vera = os.replace
    chiamate = {"n": 0}

    def replace_che_si_ferma(a, b):
        chiamate["n"] += 1
        if chiamate["n"] == 3:
            raise KeyboardInterrupt("spento a metà")
        return vera(a, b)

    os.replace = replace_che_si_ferma
    try:
        C.converti_audio(cfg, log=log.append)
        fermata = False
    except KeyboardInterrupt:
        fermata = True
    finally:
        os.replace = vera
    formati = [C.formato_wav(p.read_bytes()) for p in vecchi]
    verifica("interrotta al terzo file: due convertiti, gli altri vecchi e interi",
             fermata and formati == ["g711", "g711", "vecchio", "vecchio", "vecchio"]
             and all(p.read_bytes() == vecchio_a for p in vecchi[2:]), formati)
    verifica("interrotta: niente temporanei lasciati", not list(giro.glob("*" + C.TEMPORANEO_CONV)))
    # Un crollo vero (corrente staccata) lascerebbe il temporaneo: il rilancio lo toglie
    (giro / ("3.wav" + C.TEMPORANEO_CONV)).write_bytes(b_nuovo[:100])
    r3 = C.converti_audio(cfg, log=log.append)
    verifica("rilancio dopo l'interruzione: i 3 rimasti convertiti, il temporaneo tolto, "
             "i due di prima non riconvertiti",
             r3["convertiti"] == 3 and r3["temporanei"] == 1 and r3["gia_nuovi"] == 6
             and all(C.formato_wav(p.read_bytes()) == "g711" for p in vecchi)
             and not list(giro.glob("*" + C.TEMPORANEO_CONV)), r3)
    verifica("dopo il rilancio l'onda è giusta in tutti", all(
        snr(TONO, lettore_standard(p.read_bytes())[0]) > 28 for p in vecchi))
    verifica("sparito: un file che non c'è più",
             C.converti_file(giro / "non-c-e.wav") == ("sparito", 0))

    # Senza cartelle né memoria: niente da fare, nessun errore
    r4 = C.converti_audio(SimpleNamespace(turn_log_dir=str(tmp / "vuota"), memory_db=""),
                          log=log.append)
    verifica("senza dati: zero, nessun errore", r4["convertiti"] == 0 and r4["errori"] == 0, r4)

    # ───────── da terminale ─────────
    C._scrivi_privato(reg / "voce" / "p-adu" / "2026-10-13" / "1.wav", vecchio_a)
    env = {k: os.environ.get(k) for k in ("CALLIOPE_TURN_LOG", "CALLIOPE_CONFIG",
                                          "CALLIOPE_CONFIG_LOCALE", "CALLIOPE_MEMORY_DB")}
    try:
        os.environ["CALLIOPE_TURN_LOG"] = str(reg)
        os.environ["CALLIOPE_CONFIG"] = str(tmp / "calliope.yaml")
        os.environ["CALLIOPE_CONFIG_LOCALE"] = str(tmp / "calliope.locale.yaml")
        os.environ["CALLIOPE_MEMORY_DB"] = str(db)
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            rc = C.main(["--converti-audio"])
        # Il solo avviso della configurazione assente (cartella temporanea della prova) a parte
        testo = "\n".join(r for r in out.getvalue().splitlines() if not r.startswith("[CONFIG]"))
        verifica("terminale: --converti-audio converte e dice solo conteggi",
                 rc == 0 and "Audio riscritto nel G.711 vero: 1 file" in testo
                 and "p-adu" not in testo and str(tmp) not in testo, testo)
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            rc = C.main(["--converti-audio"])
        verifica("terminale: rilanciato, 0 file", rc == 0
                 and "Audio riscritto nel G.711 vero: 0 file." in out.getvalue(), out.getvalue())
    finally:
        for k, v in env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
finally:
    shutil.rmtree(tmp, ignore_errors=True)

print(f"\n{'Tutto bene' if not errori else f'{errori} errori'}.")
sys.exit(1 if errori else 0)
