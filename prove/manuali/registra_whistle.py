"""Registrazione delle frasi mirate per la misura di Whistle (10/10, docs/ricerche/2026-10-10-whistle.md).

Le forme chiuse brevi che whisper.cpp storpia (sospendilo, annulla, chiudilo, ricominciamo,
«Calliope, che ore sono», «Calliope, ok») e i nomi di fantasia da dare come parole suggerite
non ci sono nelle registrazioni di settembre: questo script le fa dire, una alla volta, dal
microfono predefinito (o da CALLIOPE_INPUT_DEVICE), a 16 kHz mono, e le salva in
registrazioni/<data>-whistle/ con atteso.tsv (il testo che si doveva dire, il riferimento) e
trascrizioni.tsv vuoto di proposito (qui non trascrive nessuno).

  python prove\\manuali\\registra_whistle.py [--cartella DIR] [--frasi FILE.tsv] [--da f05]

Per ogni frase: Invio per cominciare a parlare, Invio per fermare; «r» + Invio la rifà, «s»
+ Invio la salta, «q» + Invio esce (quello già registrato resta). Non fa parte del runner:
senza sounddevice o senza microfono esce con 77. Le registrazioni sono private: registrazioni/
è fuori da git.
"""
import datetime
import os
import sys
import wave
from pathlib import Path

RADICE = Path(__file__).resolve().parents[2]
SR = 16000


def opzione(nome, predefinito=None):
    if nome in sys.argv:
        i = sys.argv.index(nome)
        return sys.argv[i + 1]
    return predefinito


def registra(sd, np, dispositivo):
    blocchi = []
    with sd.InputStream(samplerate=SR, channels=1, dtype="int16", device=dispositivo,
                        callback=lambda d, *_: blocchi.append(d.copy())):
        input("  ● registro… Invio per fermare ")
    return np.concatenate(blocchi)[:, 0] if blocchi else np.zeros(0, np.int16)


def main():
    try:
        import numpy as np
        import sounddevice as sd
    except ImportError:
        print("Serve sounddevice (venv di Calliope): registrazione saltata.")
        sys.exit(77)
    frasi_f = Path(opzione("--frasi", Path(__file__).with_name("frasi_whistle.tsv")))
    righe = [r.split("\t") for r in frasi_f.read_text(encoding="utf-8").splitlines()[1:] if r.strip()]
    oggi = datetime.date.today().isoformat()
    cartella = Path(opzione("--cartella", RADICE / "registrazioni" / f"{oggi}-whistle"))
    cartella.mkdir(parents=True, exist_ok=True)
    dispositivo = os.environ.get("CALLIOPE_INPUT_DEVICE") or None
    if dispositivo and dispositivo.isdigit():
        dispositivo = int(dispositivo)
    try:
        sd.check_input_settings(device=dispositivo, samplerate=SR, channels=1, dtype="int16")
    except Exception as e:  # noqa: BLE001
        print(f"Microfono non utilizzabile a 16 kHz mono: {e}")
        sys.exit(77)
    atteso = cartella / "atteso.tsv"
    fatte = {}
    if atteso.exists():
        for r in atteso.read_text(encoding="utf-8").splitlines()[1:]:
            c = r.split("\t")
            fatte[c[0]] = r
    (cartella / "trascrizioni.tsv").touch()
    da = opzione("--da")
    print(f"Salvo in {cartella}. Parla con il tono di sempre, alla distanza di sempre dal portatile.\n")
    for i, (fid, testo, *_parole) in enumerate(righe, 1):
        if da and fid < da:
            continue
        while True:
            print(f"[{i}/{len(righe)}] {fid}: «{testo}»")
            s = input("  Invio per cominciare (s salta, q esce) ").strip().lower()
            if s == "q":
                return
            if s == "s":
                break
            audio = registra(sd, np, dispositivo)
            dur = len(audio) / SR
            print(f"  {dur:.1f} s, picco {int(np.abs(audio).max()) if len(audio) else 0}")
            s = input("  Invio per tenerla, r per rifarla ").strip().lower()
            if s == "r":
                continue
            stem = f"{fid}-{datetime.datetime.now():%H%M%S}"
            with wave.open(str(cartella / f"{stem}.wav"), "wb") as w:
                w.setnchannels(1)
                w.setsampwidth(2)
                w.setframerate(SR)
                w.writeframes(audio.tobytes())
            fatte[stem] = f"{stem}\t{testo}"
            atteso.write_text("stem\ttesto\n" + "\n".join(fatte.values()) + "\n", encoding="utf-8")
            break
    print(f"\nFatto: {len(fatte)} frasi in {cartella}.")


if __name__ == "__main__":
    main()
