# Installazione leggera del satellite su un PC Windows senza Calliope completa (02/10/2026).
# Dalla cartella del repository (o di una sua copia):
#
#     powershell -ExecutionPolicy Bypass -File setup\satellite\installa.ps1
#
# Crea .venv-satellite con le sole librerie del satellite (setup\satellite\requisiti.txt, ~120 MB
# contro i ~3,5 GB del venv completo: niente Whisper, Piper, torch) e Silero VAD senza le sue
# dipendenze. Sul portatile di sviluppo non serve: il venv di Calliope ha già tutto.
# Servono anche i tre modelli della wake word in wakeword\modelli\ (calliope.onnx,
# melspectrogram.onnx, embedding_model.onnx, ~3 MB, fuori da git): copiali dal PC dove
# Calliope è installata.
# Dal 03/10 un PC senza niente installato (né Python né il repository) si installa con il
# comando della pagina https://<server>:8770/satellite, che si aggiorna anche da solo
# (calliope/satellite/installazione/installa.ps1, prove/LEGGIMI.md). Questo script resta per
# un satellite dal repository, che non si aggiorna mai da solo.
$ErrorActionPreference = "Stop"
$radice = Resolve-Path (Join-Path $PSScriptRoot "..\..")
Set-Location $radice
$venv = Join-Path $radice ".venv-satellite"
if (-not (Test-Path (Join-Path $venv "Scripts\python.exe"))) {
    Write-Host "Creo $venv…"
    python -m venv $venv
}
$py = Join-Path $venv "Scripts\python.exe"
& $py -m pip install --upgrade pip
& $py -m pip install -r (Join-Path $PSScriptRoot "requisiti.txt")
# Solo il file ONNX del VAD (calliope/vad.py lo trova senza importare il pacchetto)
& $py -m pip install --no-deps "silero-vad==6.2.3"
$mancano = @("calliope.onnx", "melspectrogram.onnx", "embedding_model.onnx") |
    Where-Object { -not (Test-Path (Join-Path $radice "wakeword\modelli\$_")) }
if ($mancano) {
    Write-Host "Mancano i modelli della wake word in wakeword\modelli\: $($mancano -join ', ')"
}
Write-Host "Fatto. Avvio: setup\satellite\avvia_satellite.cmd (la prima volta mostra il codice"
Write-Host "di abbinamento da scrivere sul server)."
