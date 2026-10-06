"""Wrapper per avviare Calliope con microfono e cuffie specifici.

I dispositivi si scelgono per nome e non per numero: quando le cuffie Bluetooth si
ricollegano, Windows rinumera i dispositivi (il 24/09/2026 il numero delle cuffie
è finito all'altoparlante del portatile). Se mancano, Calliope usa quelli predefiniti.
Equivale a `python -m calliope` con queste due variabili d'ambiente, che vincono su
calliope.yaml.
"""
import os

# Vanno impostate prima di caricare la configurazione
os.environ.setdefault("CALLIOPE_INPUT_DEVICE", "C920 MME")   # webcam C920, API MME
os.environ.setdefault("CALLIOPE_OUTPUT_DEVICE", "I52 MME")  # cuffie Bluetooth I52, API MME

from calliope.main import main  # noqa: E402

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nCiao!")
