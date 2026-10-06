# Avvio automatico del satellite all'accesso a Windows (facoltativo, 02/10/2026):
#
#     powershell -ExecutionPolicy Bypass -File setup\satellite\avvio_automatico.ps1          aggiunge
#     powershell -ExecutionPolicy Bypass -File setup\satellite\avvio_automatico.ps1 -Togli    toglie
#
# Un collegamento a avvia_satellite.cmd nella cartella Esecuzione automatica dell'utente
# (shell:startup), con la finestra ridotta a icona: niente servizi né permessi di
# amministratore (il satellite usa microfono e casse della sessione dell'utente).
param([switch]$Togli)
$ErrorActionPreference = "Stop"
$avvio = [Environment]::GetFolderPath("Startup")
$link = Join-Path $avvio "Satellite di Calliope.lnk"
if ($Togli) {
    if (Test-Path $link) { Remove-Item $link; Write-Host "Tolto: $link" }
    else { Write-Host "Non c'era." }
    exit 0
}
$cmd = Join-Path $PSScriptRoot "avvia_satellite.cmd"
$shell = New-Object -ComObject WScript.Shell
$s = $shell.CreateShortcut($link)
$s.TargetPath = $cmd
$s.WorkingDirectory = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$s.WindowStyle = 7          # ridotta a icona
$s.Description = "Satellite di Calliope: microfono e casse per Calliope sul server"
$s.Save()
Write-Host "Aggiunto: $link (parte al prossimo accesso; per toglierlo: -Togli)"
