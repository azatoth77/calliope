"""
Calliope — assistente vocale locale.

Pipeline: microfono → Silero VAD → wake word acustica → faster-whisper → Ollama
(streaming, tool) → Piper → altoparlanti. Avvio: `python -m calliope` (o
`python avvia_calliope.py`); configurazione in calliope.yaml (vedi config.py).

Il package non importa nulla qui: i moduli si caricano solo quando servono, così gli
script (prove, addestramento della wake word) possono usarne uno senza tirarsi dietro
Whisper, Piper e sounddevice.
"""
