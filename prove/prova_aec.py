import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

USO = r"""Cancellazione dell'eco (AEC) per il barge-in di «livello B»: prova di fattibilità.

Non tocca Calliope: lancia gli script di docs/ricerche/banchi/aec/ nell'ordine giusto e con il venv giusto.
I motori AEC (livekit/WebRTC AEC3, speexdsp via pyaec, DTLN-aec via LiteRT) stanno nel
venv separato docs\ricerche\banchi\aec\.venv; Piper, Silero VAD e Whisper nel .venv principale.

Uso (dalla radice del progetto):
    $env:PYTHONUTF8=1
    .\.venv\Scripts\python.exe prove\prova_aec.py tutto           # passi 1, 3, 4 (niente audio in uscita)
    .\.venv\Scripts\python.exe prove\prova_aec.py riferimenti     # 1. voce di Calliope con Piper
    .\.venv\Scripts\python.exe prove\prova_aec.py misura [opzioni] # 2. riproduce e registra (FA RUMORE)
    .\.venv\Scripts\python.exe prove\prova_aec.py simula [opzioni] # 3. eco simulata + motori AEC
    .\.venv\Scripts\python.exe prove\prova_aec.py valuta [opzioni] # 4. VAD e Whisper sulle uscite

Preparazione una tantum del venv separato (vedi docs/ricerche/2026-09-26-cancellazione-eco.md):
    py -3.14 -m venv docs\ricerche\banchi\aec\.venv
    docs\ricerche\banchi\aec\.venv\Scripts\python.exe -m pip install numpy scipy soundfile soxr sounddevice livekit pyaec ai-edge-litert
    (modelli DTLN-aec in docs\ricerche\banchi\aec\modelli\dtln\, da github.com/breizhn/DTLN-aec/pretrained_models)
"""
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / ".venv" / "Scripts" / "python.exe"
BANCO = ROOT / "docs" / "ricerche" / "banchi" / "aec"
AEC = BANCO / ".venv" / "Scripts" / "python.exe"

PASSI = {
    "riferimenti": (MAIN, "genera_riferimenti.py"),
    "misura": (AEC, "misura_reale.py"),
    "reale": (AEC, "reale_aec.py"),
    "simula": (AEC, "simula.py"),
    "valuta": (MAIN, "valuta.py"),
}


def run(passo, args=()):
    py, script = PASSI[passo]
    if not py.exists():
        sys.exit(f"Manca {py}: vedi le istruzioni in testa a questo file")
    env = dict(os.environ, PYTHONUTF8="1")
    print(f"--- {passo}: {script} {' '.join(args)}", flush=True)
    r = subprocess.run([str(py), "-u", script, *args], cwd=BANCO, env=env)
    if r.returncode:
        sys.exit(r.returncode)


def main():
    if len(sys.argv) < 2 or sys.argv[1] not in (*PASSI, "tutto"):
        print(USO)
        sys.exit(1)
    if sys.argv[1] == "tutto":
        for p in ("riferimenti", "simula", "reale", "valuta"):
            if p == "reale" and not (BANCO / "dati" / "reale").exists():
                continue            # la misura reale va lanciata a mano: fa rumore
            run(p)
    else:
        run(sys.argv[1], sys.argv[2:])


if __name__ == "__main__":
    main()
