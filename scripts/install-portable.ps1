param(
    [string]$CoopanionRoot,
    [string]$BotId = 'companion',
    [string]$DeviceName,
    [switch]$RuntimeOnly,
    [switch]$NoLaunch,
    [switch]$NoEnableSpeech
)
$ErrorActionPreference='Stop'
$bundleRoot=Split-Path $PSScriptRoot -Parent
$env:PYTHONUTF8='1'
$voicePython=Join-Path $bundleRoot 'python/python.exe'
if (-not (Test-Path -LiteralPath (Join-Path $bundleRoot 'portable-manifest.json'))) { throw 'Run this from the extracted portable ZIP.' }
if ($bundleRoot -match '[^\x00-\x7F]') { throw 'Extract the ZIP to an English path, for example D:\CoopanionVoice, then run install.cmd again.' }
Write-Host 'Coopanion Lightweight Local Voice Engine | Asryto'
if (-not $RuntimeOnly) {
    if (-not $CoopanionRoot) {
        . (Join-Path $PSScriptRoot 'find-coopanion.ps1')
        $detected=@(Find-CoopanionDirectory)
        if ($detected.Count -eq 1) { $CoopanionRoot=$detected[0];Write-Host ('Detected Coopanion: '+$CoopanionRoot) }
        else {
            if ($detected.Count -gt 1) { Write-Host 'Multiple Coopanion installations found. Select the one you use:';$detected | ForEach-Object { Write-Host $_ } }
            else { Write-Host 'Coopanion was not found automatically. Select its installation directory.' }
            Add-Type -AssemblyName System.Windows.Forms
            $picker=New-Object System.Windows.Forms.FolderBrowserDialog
            $picker.Description='Select the directory containing Coopanion.exe'
            if ($picker.ShowDialog() -ne [System.Windows.Forms.DialogResult]::OK) { throw 'No Coopanion directory selected.' }
            $CoopanionRoot=$picker.SelectedPath
        }
    }
    $appRoot=(Resolve-Path -LiteralPath $CoopanionRoot).Path
    if ($BotId -match '[/\\]' -or $BotId -in @('.','..')) { throw 'Invalid BotId.' }
    $extensions=Join-Path $appRoot 'data/extensions';$bot=Join-Path $appRoot ('data/home/'+$BotId)
    foreach ($file in @((Join-Path $extensions 'package.json'),(Join-Path $bot 'config.json'))) {
        if (-not (Test-Path -LiteralPath $file -PathType Leaf)) { throw "Initialize Coopanion once before installing voice. Missing: $file" }
    }
    $petMeta=Join-Path $appRoot 'resources/app/node_modules/cortico-world-desktop-pet/package.json'
    $running=Get-CimInstance Win32_Process -Filter "Name='Coopanion.exe'" | Where-Object { $_.ExecutablePath -eq (Join-Path $appRoot 'Coopanion.exe') }
    if ($running) {
        if (-not (Test-Path -LiteralPath $petMeta) -or (Get-Content -LiteralPath $petMeta -Raw | ConvertFrom-Json).version -ne '0.1.4') { throw 'Exit Coopanion, then run install.cmd again.' }
        Write-Host 'Closing Coopanion gracefully before extension installation...'
        $socket=New-Object System.Net.WebSockets.ClientWebSocket
        try {
            $socket.Options.SetRequestHeader('Origin','http://127.0.0.1:7797')
            $connect=$socket.ConnectAsync([Uri]'ws://127.0.0.1:7797/socket?role=pet&host=tab',[Threading.CancellationToken]::None)
            if (-not $connect.Wait(5000)) { throw 'Quit connection timed out. Exit Coopanion manually.' }
            $bytes=[Text.Encoding]::UTF8.GetBytes('{"t":"control","action":"quit"}')
            $socket.SendAsync([ArraySegment[byte]]::new($bytes),[Net.WebSockets.WebSocketMessageType]::Text,$true,[Threading.CancellationToken]::None).GetAwaiter().GetResult()
            foreach ($process in $running) { Wait-Process -Id $process.ProcessId -Timeout 10 -ErrorAction SilentlyContinue }
        } finally { $socket.Dispose() }
        if (Get-CimInstance Win32_Process -Filter "Name='Coopanion.exe'" | Where-Object { $_.ExecutablePath -eq (Join-Path $appRoot 'Coopanion.exe') }) { throw 'Coopanion is still running. Exit it and retry.' }
    }
}
$log=Join-Path $bundleRoot 'installation.log'
# Windows PowerShell 5.1 wraps native stderr as non-terminating errors.
# Native libraries write ordinary diagnostics there; the exit code is authoritative.
$ErrorActionPreference='Continue'
Write-Host '[1/3] Checking bundled model and selecting the integrated GPU...'
$bindArgs=@('--root',$bundleRoot);if ($DeviceName) { $bindArgs+=@('--device-name',$DeviceName) }
$bound=& $voicePython (Join-Path $PSScriptRoot 'activate_portable.py') @bindArgs 2>>$log
if ($LASTEXITCODE -ne 0) { throw "Runtime verification failed. See $log" }
$device=($bound | ConvertFrom-Json).device;Write-Host "GPU: $device"
Write-Host '[2/3] Testing real synthesis and muted playback...'
$verify=& $voicePython (Join-Path $PSScriptRoot 'verify_deployment.py') --runtime $bundleRoot --output (Join-Path $bundleRoot 'verification') 2>>$log
if ($LASTEXITCODE -ne 0) { throw "Speech verification failed. See $log" }
$report=$verify | ConvertFrom-Json
Write-Host ('Audio: '+$report.playback.seconds+' seconds; first callback: '+$report.playback.firstDeviceCallbackMs+' ms')
if (-not $RuntimeOnly) {
    Write-Host '[3/3] Installing the independent World and preserving personal settings...'
    $worldArgs=@('--extensions',$extensions,'--bot',$bot,'--runtime',$bundleRoot)
    if (-not $NoEnableSpeech) { $worldArgs+='--enable' }
    & $voicePython (Join-Path $PSScriptRoot 'install_world.py') @worldArgs 2>>$log
    if ($LASTEXITCODE -ne 0) { throw "Extension installation failed. See $log" }
    if (-not $NoLaunch -and (Test-Path -LiteralPath (Join-Path $appRoot 'Coopanion.exe'))) {
        Start-Process -FilePath (Join-Path $appRoot 'Coopanion.exe') -WorkingDirectory $appRoot -WindowStyle Hidden
    }
    Write-Host 'Installed. Open Lightweight Local Voice Engine in Coopanion. Bubble sync is a separate option.'
} else { Write-Host 'Runtime verified. World connection was not requested.' }
Write-Host ('Report: '+(Join-Path $bundleRoot 'verification/deployment-check.json'))
