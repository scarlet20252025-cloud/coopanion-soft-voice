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

}
$log=Join-Path $bundleRoot 'installation.log'
# Windows PowerShell 5.1 wraps native stderr as non-terminating errors.
# Native libraries write ordinary diagnostics there; the exit code is authoritative.
$ErrorActionPreference='Continue'
# Machines without an integrated GPU cannot use the automatic default, and a
# discrete GPU is never chosen implicitly. Ask before binding instead of
# failing later with an empty integrated-device list.
Write-Host '[1/3] Checking bundled model and selecting the GPU...'
if (-not $DeviceName) {
    # A machine without a Vulkan driver prints nothing here; treat that as a
    # driver problem instead of failing inside ConvertFrom-Json.
    $inventoryText=(& $voicePython (Join-Path $PSScriptRoot 'activate_portable.py') --list-devices 2>>$log | Out-String).Trim()
    $inventory=$null
    if ($inventoryText) { try { $inventory=$inventoryText|ConvertFrom-Json } catch { $inventory=$null } }
    $gpus=@();$integrated=@()
    if ($inventory) { $gpus=@($inventory.devices);$integrated=@($inventory.integrated) }
    if (-not $gpus.Count) { throw 'No Vulkan GPU was detected. Install the vendor graphics driver, then run install.cmd again; details are in installation.log.' }
    if ($integrated.Count -ne 1) {
        Write-Host ''
        Write-Host 'This machine does not have exactly one integrated GPU, so the automatic default cannot be used.'
        Write-Host 'Choose the device that should run speech:'
        for ($i=0;$i -lt $gpus.Count;$i++) {
            $kind=if ($gpus[$i].kind -eq 'discrete') { 'discrete; shares VRAM with games' } else { 'integrated' }
            Write-Host ('  [{0}] {1}  ({2})' -f ($i+1),$gpus[$i].name,$kind)
        }
        if ([Console]::IsInputRedirected) {
            throw ('No integrated GPU is available, so -DeviceName is required. Re-run with: powershell -NoProfile -ExecutionPolicy Bypass -File scripts\install-portable.ps1 -DeviceName "'+$gpus[0].name+'"')
        }
        $answer=Read-Host ('Press Enter to use 1, or type the number to use (1-'+$gpus.Count+')')
        $pick=1
        if (-not [string]::IsNullOrWhiteSpace($answer)) {
            if (-not [int]::TryParse($answer.Trim(),[ref]$pick)) { throw 'That was not a number; nothing was changed.' }
        }
        if ($pick -lt 1 -or $pick -gt $gpus.Count) { throw 'That number is not in the list; nothing was changed.' }
        $DeviceName=$gpus[$pick-1].name
        Write-Host ('Selected device: '+$DeviceName)
    }
}
$bindArgs=@('--root',$bundleRoot);if ($DeviceName) { $bindArgs+=@('--device-name',$DeviceName) }
$bound=& $voicePython (Join-Path $PSScriptRoot 'activate_portable.py') @bindArgs 2>>$log
if ($LASTEXITCODE -ne 0) { throw "Runtime verification failed. See $log" }
$device=($bound | ConvertFrom-Json).device;Write-Host "GPU: $device"
Write-Host '[2/3] Testing real synthesis and muted playback...'
$verify=& $voicePython (Join-Path $PSScriptRoot 'verify_deployment.py') --runtime $bundleRoot --output (Join-Path $bundleRoot 'verification') 2>>$log
if ($LASTEXITCODE -ne 0) { throw "Speech verification failed. See $log" }
$report=$verify | ConvertFrom-Json
Write-Host ('Audio: '+$report.playback.seconds+' seconds; first callback: '+$report.playback.firstDeviceCallbackMs+' ms')
Write-Host ('Playback: '+$report.playback.effectivePlaybackMode+'; RTF: '+$report.playback.realTimeFactor+'; underrun: '+$report.playback.underrunMs+' ms')
if (-not $report.playbackHealth.smooth) { Write-Warning 'Audio device starvation was detected. Installation succeeded, but smooth playback was NOT verified. Select buffered playback and retest.' }
elseif (-not $report.playbackHealth.streamingRecommended) { Write-Host 'This GPU uses complete-utterance buffering for smooth audio. Expect longer startup; faster streaming was not verified.' }
if (-not $RuntimeOnly) {
    Write-Host '[3/3] Detecting the installed extension version (marketplace or offline)...'
    $planRaw=& $voicePython (Join-Path $PSScriptRoot 'install_world.py') --extensions $extensions --bot $bot --runtime $bundleRoot --inspect 2>>$log
    if ($LASTEXITCODE -ne 0) { throw "Extension version check failed. See $log" }
    $plan=$planRaw | ConvertFrom-Json
    if ($plan.action -eq 'skip') { Write-Host ('Keeping installed extension '+$plan.installedVersion+'; bundled '+$plan.bundledVersion+'. Model setup still completes.') }
    else { Write-Host ('Extension '+$plan.action+': '+$plan.installedVersion+' -> '+$plan.bundledVersion) }
    $petMeta=Join-Path $appRoot 'resources/app/node_modules/cortico-world-desktop-pet/package.json'
    $running=Get-CimInstance Win32_Process -Filter "Name='Coopanion.exe'" | Where-Object { $_.ExecutablePath -eq (Join-Path $appRoot 'Coopanion.exe') }
    if ($running) {
        if (-not (Test-Path -LiteralPath $petMeta) -or (Get-Content -LiteralPath $petMeta -Raw | ConvertFrom-Json).version -ne '0.1.4') { throw 'Exit Coopanion, then run install.cmd again.' }
        Add-Type -AssemblyName System.Windows.Forms
        $restartChoice=[System.Windows.Forms.MessageBox]::Show('Installation needs to close Coopanion and restart it afterwards. Continue now? Choose No to keep using it and install later.','Coopanion voice installation',[System.Windows.Forms.MessageBoxButtons]::YesNo,[System.Windows.Forms.MessageBoxIcon]::Question)
        if ($restartChoice -ne [System.Windows.Forms.DialogResult]::Yes) { Write-Host 'Model verified. Installation postponed; Coopanion is unchanged.';return }
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
