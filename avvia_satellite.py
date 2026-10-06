"""Avvia il satellite (calliope/satellite/) con microfono e cuffie scelti per nome.

Come avvia_calliope.py: i dispositivi per nome e non per numero, perché Windows rinumera
quando le cuffie Bluetooth si ricollegano; se mancano si usano quelli predefiniti
(`scegli_dispositivi`, che stampa quali). Dal 05/10 questi nomi valgono solo se la
configurazione non ne sceglie altri: calliope.locale.yaml, sezione satellite
(satellite_microfono, satellite_casse, satellite_webcam), o le variabili
CALLIOPE_SATELLITE_MICROFONO, CALLIOPE_SATELLITE_CASSE, CALLIOPE_SATELLITE_WEBCAM. L'indirizzo
del server sta nella stessa sezione (satellite_server) o in CALLIOPE_SATELLITE_SERVER.
"""
import sys

from calliope.satellite.__main__ import main

PREDEFINITI = {
    "satellite_microfono": "C920 MME",   # webcam C920, API MME
    "satellite_casse": "I52 MME",        # cuffie Bluetooth I52, API MME
}

if __name__ == "__main__":
    sys.exit(main(predefiniti=PREDEFINITI))
