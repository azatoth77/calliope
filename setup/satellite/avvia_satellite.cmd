@echo off
rem Avvia il satellite di Calliope (calliope/satellite/) dalla cartella del repository.
rem Usa il venv completo di Calliope se c'e', altrimenti quello leggero di installa.ps1.
rem Doppio clic, oppure il collegamento creato da avvio_automatico.ps1 (avvio all'accesso).
cd /d "%~dp0..\.."
set PY=.venv\Scripts\python.exe
if not exist "%PY%" set PY=.venv-satellite\Scripts\python.exe
if not exist "%PY%" (
    echo Manca il venv: lancia setup\satellite\installa.ps1
    pause
    exit /b 1
)
set PYTHONUTF8=1
"%PY%" -u avvia_satellite.py %*
if errorlevel 1 pause
