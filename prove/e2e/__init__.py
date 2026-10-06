"""
Prove end-to-end su una Calliope di prova (06/10/2026): una seconda Calliope sulla DGX, dal
codice della versione in uso, con la sua cartella dati (`~/calliope-e2e/`), le sue porte, lo
stesso Ollama, vLLM e Whisper della Calliope vera, Home Assistant e PC finti, e satelliti
finti che parlano con il protocollo vero (VAD e wake word veri, frasi di Piper o registrate).

    python -m prove.e2e.lancia            # dal portatile: copia, esegue sulla DGX, riporta
    python -m prove.e2e [--aree casa,…]   # sulla DGX, dentro la versione (lo fa lancia.py)

Moduli:
  voci.py      persone di prova, frasi di Piper e registrazioni vere (solo sulla DGX, cancellate)
  istanza.py   configurazione, profili, abbinamenti, avvio e arresto della Calliope di prova,
               guardia sulla Calliope vera (si parla solo se è ferma da 180 s)
  satelliti.py satellite vero (calliope/satellite/client.py) con microfono e casse finti
  copioni.py   le conversazioni, con cosa ci si aspetta da ogni turno
  verifica.py  controllo dei turni sul registro dell'istanza e sulle frasi sentite
  __main__.py  il runner (sulla DGX)
  lancia.py    il comando unico dal portatile

Documentazione: prove/manuali/e2e-dgx.md.
"""
