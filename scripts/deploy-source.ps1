param(
    [string]$Python = 'py',
    [string]$Runtime,
    [string]$DeviceName,
    [string]$Cache,
    [string]$CoopanionRoot,
    [string]$BotId = 'companion',
    [string]$Extensions,
    [string]$Bot,
    [switch]$FullModel,
    [switch]$EnableSpeech
)
$ErrorActionPreference = 'Stop'
$project = Split-Path $PSScriptRoot -Parent
if (-not $Runtime) { $Runtime = Join-Path $project '.runtime-native' }
$Runtime = [IO.Path]::GetFullPath($Runtime)
if ($CoopanionRoot) {
    $appRoot = (Resolve-Path -LiteralPath $CoopanionRoot).Path
    if ($Extensions -or $Bot) { throw 'Use either -CoopanionRoot or the explicit -Extensions/-Bot pair.' }
    if ($BotId -match '[/\\]' -or $BotId -in @('.', '..')) { throw 'BotId must be one directory name.' }
    $Extensions = Join-Path $appRoot 'data/extensions'
    $Bot = Join-Path $appRoot ('data/home/' + $BotId)
}
if ([bool]$Extensions -ne [bool]$Bot) { throw 'Provide both -Extensions and -Bot.' }
if ($Extensions) {
    foreach ($file in @((Join-Path $Extensions 'package.json'), (Join-Path $Bot 'config.json'))) {
        if (-not (Test-Path -LiteralPath $file -PathType Leaf)) { throw "Coopanion configuration missing: $file" }
    }
    if (Get-Process -Name Coopanion -ErrorAction SilentlyContinue) { throw 'Exit Coopanion before installing the extension.' }
}
$nativeArgs = @{Python=$Python;Runtime=$Runtime}
if ($DeviceName) { $nativeArgs.DeviceName=$DeviceName }
if ($Cache) { $nativeArgs.Cache=$Cache }
& (Join-Path $PSScriptRoot 'setup-native.ps1') @nativeArgs
$voicePython = Join-Path $Runtime 'venv/Scripts/python.exe'
$selectedRuntime = $Runtime
if (-not $FullModel) {
    $profileJson = & $voicePython (Join-Path $PSScriptRoot 'prepare_speech_profile.py') --runtime $Runtime
    if ($LASTEXITCODE -ne 0) { throw 'Fixed-reference profile build/verification failed.' }
    $selectedRuntime = ($profileJson | ConvertFrom-Json).runtime
}
& $voicePython (Join-Path $PSScriptRoot 'verify_deployment.py') --runtime $selectedRuntime --output (Join-Path $Runtime 'verification')
if ($LASTEXITCODE -ne 0) { throw 'Actual synthesis/playback verification failed; extension not installed.' }
if ($Extensions) {
    $installArgs = @('--extensions', $Extensions, '--bot', $Bot, '--runtime', $selectedRuntime)
    if ($EnableSpeech) { $installArgs += '--enable' }
    & $voicePython (Join-Path $PSScriptRoot 'install_world.py') @installArgs
    if ($LASTEXITCODE -ne 0) { throw 'World installation failed. Read the preserved backup and error.' }
}
Write-Host "Verified voice runtime: $selectedRuntime"
Write-Host "Python: $voicePython"
Write-Host "Deployment report: $(Join-Path $Runtime 'verification/deployment-check.json')"
if ($Extensions) { Write-Host 'World installed. Start Coopanion and open Local Voice Assistant.' }
else { Write-Host 'Runtime ready. Supply -CoopanionRoot or -Extensions/-Bot to connect a desktop pet.' }
