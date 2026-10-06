"""`python -m calliope`: avvia Calliope."""
import sys

USAGE = """Calliope — assistente vocale locale.

Uso:
  python -m calliope                 avvia Calliope (configurazione in calliope.yaml)
  python avvia_calliope.py           come sopra, con webcam C920 e cuffie I52 per nome
  python -m calliope.config --esempio > calliope.yaml
                                     rigenera il file di configurazione dai commenti

Variabili d'ambiente (vincono su calliope.yaml): CALLIOPE_CONFIG (percorso del file),
CALLIOPE_INPUT_DEVICE, CALLIOPE_OUTPUT_DEVICE, CALLIOPE_WAKE_MODE, CALLIOPE_PIPER_VOICE,
CALLIOPE_MEMORY_DB, CALLIOPE_TURN_LOG, CALLIOPE_DEBUG_AUDIO."""


def cli():
    """`python -m calliope` e il comando `calliope` del venv (pyproject.toml)."""
    if {"-h", "--help", "/?"} & set(sys.argv[1:]):
        print(USAGE)
        sys.exit(0)
    from .main import main
    try:
        main()
    except KeyboardInterrupt:
        print("\nCiao!")


if __name__ == "__main__":
    cli()
