# Un PC Windows nuovo diventa satellite di Calliope (03/10/2026). Lo scarica e lo lancia il
# comando della pagina /satellite del server (calliope/satellite/web.py), che controlla la
# chiave del certificato del server. Funziona con Windows PowerShell 5.1 di un PC appena
# installato; niente diritti di amministratore: tutto in %LOCALAPPDATA%\Calliope\satellite.
#
#   -Server   https://<server>:8771 (la porta dei satelliti)
#   -Chiave   sha256//<base64>: la chiave pubblica del certificato del server; OGNI download
#             dal server passa da curl.exe --pinnedpubkey con questa chiave
#   -AvvioAutomatico si|no   senza: lo chiede
#   -NonAvviare             non avvia il satellite alla fine
#   -FinoAlPacchetto        si ferma dopo aver scaricato e verificato manifesto e pacchetto
#                           (le prove a secco)
#   -Uv <uv.exe>            usa questo uv invece di scaricarlo (le prove)
param(
    [Parameter(Mandatory = $true)][string]$Server,
    [Parameter(Mandatory = $true)][string]$Chiave,
    [string]$Cartella = "",
    [string]$AvvioAutomatico = "",
    [switch]$NonAvviare,
    [switch]$FinoAlPacchetto,
    [string]$Uv = ""
)
$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
if (-not $Cartella) { $Cartella = Join-Path $env:LOCALAPPDATA "Calliope\satellite" }
$Server = $Server.TrimEnd("/")

function Fermati([string]$msg) {
    Write-Host ""
    Write-Host "Installazione fermata: $msg" -ForegroundColor Red
    exit 1
}

if ($Chiave -notmatch '^sha256//[A-Za-z0-9+/]{43}=$') { Fermati "la chiave non ha la forma sha256//<44 caratteri>." }
if ($Server -notmatch '^https://') { Fermati "il server va scritto con https://" }
$curl = Join-Path $env:SystemRoot "System32\curl.exe"
if (-not (Test-Path $curl)) { Fermati "manca curl.exe di Windows (serve Windows 10 1803 o più recente)." }

function Dal-Server([string]$percorso, [string]$dest) {
    # -k: il certificato non è di una CA che questo PC conosce; --pinnedpubkey: curl chiude la
    # connessione prima di mandare o ricevere un byte se la chiave non è quella attesa
    & $curl -fsSk --pinnedpubkey $Chiave --retry 2 -o $dest "$Server$percorso"
    if ($LASTEXITCODE -eq 90) { Fermati "la chiave del server NON è quella del comando. Non proseguire: controlla con calliope satellite --elenco sul server." }
    if ($LASTEXITCODE -ne 0) { Fermati "non riesco a scaricare $percorso dal server (curl, codice $LASTEXITCODE)." }
}

# Solo .NET e cmdlet di base: Get-FileHash ed Expand-Archive sono funzioni di moduli che
# Windows PowerShell lanciato da PowerShell 7 non trova (PSModulePath ereditato)
function Sha256([string]$p) {
    $f = [System.IO.File]::OpenRead($p)
    try { $h = [System.Security.Cryptography.SHA256]::Create().ComputeHash($f) } finally { $f.Dispose() }
    return (($h | ForEach-Object { $_.ToString("x2") }) -join "")
}
Add-Type -AssemblyName System.IO.Compression.FileSystem

Write-Host "Satellite di Calliope: installazione in $Cartella"
New-Item -ItemType Directory -Force -Path $Cartella | Out-Null
$tmp = Join-Path $Cartella "scaricati"
New-Item -ItemType Directory -Force -Path $tmp | Out-Null

# 1. Il manifesto: cosa scaricare, con quali SHA-256, dove collegarsi
$fm = Join-Path $tmp "manifesto.json"
Dal-Server "/installa/manifesto.json" $fm
try { $m = Get-Content -Raw -Encoding UTF8 -LiteralPath $fm | ConvertFrom-Json } catch { Fermati "manifesto non leggibile." }
if (-not $m.pacchetto.sha256 -or $m.pacchetto.sha256.Length -ne 64) { Fermati "manifesto senza SHA-256 del pacchetto." }
Write-Host "  server: versione $($m.pacchetto.versione) del satellite, Python $($m.python)"

# 2. Il pacchetto del satellite (codice, wake word, versioni bloccate), verificato
$fz = Join-Path $tmp "pacchetto-$($m.pacchetto.versione).zip"
Dal-Server $m.pacchetto.percorso $fz
if ((Sha256 $fz) -ne $m.pacchetto.sha256.ToLower()) { Remove-Item -Force $fz; Fermati "il pacchetto non corrisponde allo SHA-256 del manifesto." }
Write-Host "  pacchetto verificato ($([math]::Round($m.pacchetto.byte / 1MB, 1)) MB)"
if ($FinoAlPacchetto) { Write-Host "Fatto (solo download e verifica)."; exit 0 }

# 3. uv: binario ufficiale da GitHub (TLS verificato da Windows) con lo SHA-256 fissato
$cartellaUv = Join-Path $Cartella "uv"
$uvExe = Join-Path $cartellaUv "uv.exe"
if ($Uv) {
    New-Item -ItemType Directory -Force -Path $cartellaUv | Out-Null
    Copy-Item -Force -LiteralPath $Uv -Destination $uvExe
} else {
    $arm = ($env:PROCESSOR_ARCHITECTURE -eq "ARM64") -or ($env:PROCESSOR_ARCHITEW6432 -eq "ARM64")
    $arch = if ($arm) { "aarch64" } else { "x86_64" }
    $info = $m.uv.$arch
    $ok = $false
    if (Test-Path $uvExe) { $ok = ((& $uvExe --version) -match [regex]::Escape($m.uv.versione)) }
    if (-not $ok) {
        Write-Host "  scarico uv $($m.uv.versione) ($arch)…"
        $fu = Join-Path $tmp "uv.zip"
        & $curl -fsSL --retry 2 -o $fu $info.url
        if ($LASTEXITCODE -ne 0) { Fermati "non riesco a scaricare uv da GitHub (serve internet: curl, codice $LASTEXITCODE)." }
        if ((Sha256 $fu) -ne $info.sha256.ToLower()) { Remove-Item -Force $fu; Fermati "uv scaricato non corrisponde allo SHA-256 fissato." }
        if (Test-Path $cartellaUv) { Remove-Item -Recurse -Force $cartellaUv }
        [System.IO.Compression.ZipFile]::ExtractToDirectory($fu, $cartellaUv)
        Remove-Item -Force $fu
    }
}
Write-Host "  $(& $uvExe --version)"

# 4. Python (uv, versione fissata) e l'avvio dal pacchetto
$env:UV_PYTHON_INSTALL_DIR = Join-Path $Cartella "python"
$env:UV_CACHE_DIR = Join-Path $Cartella "cache"
$env:UV_NO_CONFIG = "1"
$env:UV_NO_PROGRESS = "1"
Write-Host "  Python $($m.python)…"
& $uvExe python install $m.python --no-bin --no-registry
if ($LASTEXITCODE -ne 0) { Fermati "uv non è riuscito a installare Python $($m.python)." }
$py = (& $uvExe python find --managed-python $m.python | Select-Object -First 1)
if (-not $py -or -not (Test-Path $py)) { Fermati "non trovo il Python appena installato." }
$zip = [System.IO.Compression.ZipFile]::OpenRead($fz)
try {
    $voce = $zip.Entries | Where-Object { $_.FullName -eq "calliope/satellite/installazione/avvio.py" }
    if (-not $voce) { Fermati "il pacchetto non contiene avvio.py." }
    [System.IO.Compression.ZipFileExtensions]::ExtractToFile($voce, (Join-Path $Cartella "avvio.py"), $true)
} finally { $zip.Dispose() }

# 5. La versione: codice, venv dalle versioni bloccate, verifica a secco
Write-Host "  preparo il satellite (librerie: qualche minuto la prima volta)…"
$env:CALLIOPE_SATELLITE_RADICE = $Cartella
& $py (Join-Path $Cartella "avvio.py") prepara --pacchetto $fz --sha256 $m.pacchetto.sha256 --attiva
if ($LASTEXITCODE -ne 0) { Fermati "la preparazione del satellite non è riuscita (vedi sopra)." }
Remove-Item -Force $fz

# 6. Configurazione del satellite: indirizzo del server e impronta del suo certificato
$dati = Join-Path $Cartella "dati"
New-Item -ItemType Directory -Force -Path $dati | Out-Null
$utf8 = New-Object System.Text.UTF8Encoding($false)
$fy = Join-Path $dati "calliope.yaml"
if (-not (Test-Path $fy)) {
    [System.IO.File]::WriteAllText($fy, "# Satellite installato dalla pagina /satellite: i valori sono in calliope.locale.yaml`n", $utf8)
}
$fl = Join-Path $dati "calliope.locale.yaml"
$locale = "# Scritto da installa.ps1 il $(Get-Date -Format 'dd/MM/yyyy HH:mm') (pagina /satellite del server)`n" +
          "satellite:`n" +
          "  satellite_server: `"$($m.satellite_server)`"`n" +
          "  satellite_impronta: `"$($m.satellite_impronta)`"`n" +
          "  # Microfono, casse e webcam di questo PC: parole del nome (C920 MME, I52 MME; le`n" +
          "  # righe [AUDIO] all'avvio dicono quelli in uso). Vuoti = i predefiniti di Windows`n" +
          "  satellite_microfono: null`n" +
          "  satellite_casse: null`n" +
          "  satellite_webcam: `"`"`n"
if (Test-Path $fl) {
    $vecchio = [System.IO.File]::ReadAllText($fl)
    if ($vecchio -notmatch [regex]::Escape($m.satellite_impronta)) {
        Copy-Item -Force $fl "$fl.prima"
        Write-Host "  calliope.locale.yaml c'era già: copia in calliope.locale.yaml.prima"
        [System.IO.File]::WriteAllText($fl, $locale, $utf8)
    }
} else {
    [System.IO.File]::WriteAllText($fl, $locale, $utf8)
}

# 7. Il lanciatore e l'avvio automatico all'accesso (facoltativo)
$cmd = Join-Path $Cartella "avvia.cmd"
$righe = @("@echo off",
           "rem Satellite di Calliope: avvio con gli aggiornamenti automatici (avvio.py).",
           "set PYTHONUTF8=1",
           "`"$py`" -u `"%~dp0avvio.py`" %*",
           "if errorlevel 1 pause")
[System.IO.File]::WriteAllText($cmd, ($righe -join "`r`n") + "`r`n", (New-Object System.Text.UTF8Encoding($false)))
$link = Join-Path ([Environment]::GetFolderPath("Startup")) "Satellite di Calliope.lnk"
if (-not $AvvioAutomatico) {
    $AvvioAutomatico = Read-Host "Avviare il satellite a ogni accesso a Windows? [s/N]"
}
if ($AvvioAutomatico -match '^(s|si|sì|y|yes)$') {
    $shell = New-Object -ComObject WScript.Shell
    $s = $shell.CreateShortcut($link)
    $s.TargetPath = $cmd
    $s.WorkingDirectory = $Cartella
    $s.WindowStyle = 7
    $s.Description = "Satellite di Calliope: microfono e casse per Calliope sul server"
    $s.Save()
    Write-Host "  avvio all'accesso: $link"
} elseif (Test-Path $link) {
    Write-Host "  (l'avvio all'accesso c'era già: per toglierlo cancella $link)"
}

Write-Host ""
Write-Host "Satellite installato. Per avviarlo a mano: $cmd"
if ($NonAvviare) { exit 0 }
Write-Host "Lo avvio: la prima volta mostra un codice di 6 cifre da scrivere sul server con"
Write-Host "  calliope satellite --abbina <codice> --stanza <stanza> --pc"
Write-Host "  (con --pc comanda anche questo PC: volume, file e documenti; senza, solo la voce)"
Write-Host ""
& $cmd
