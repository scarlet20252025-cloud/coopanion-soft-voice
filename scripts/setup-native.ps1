param(
    [string]$Python = 'py',
    [string]$Runtime,
    [string]$DeviceName = 'AMD Radeon(TM) Graphics',
    [string]$Cache,
    [switch]$BuildOnly
)
$ErrorActionPreference = 'Stop'
$project = Split-Path $PSScriptRoot -Parent
if (-not $Runtime) { $Runtime = Join-Path $project '.runtime-native' }
$Runtime = [IO.Path]::GetFullPath($Runtime)
New-Item -ItemType Directory -Force $Runtime | Out-Null
$pythonExe = Join-Path $Runtime 'venv/Scripts/python.exe'
if (-not (Test-Path $pythonExe)) {
    if ($Python -eq 'py') { & py -3.10 -m venv (Join-Path $Runtime 'venv') }
    else { & $Python -m venv (Join-Path $Runtime 'venv') }
    if ($LASTEXITCODE -ne 0) { throw 'Install Python 3.10 x64 and Git, then retry.' }
}
& $pythonExe -c "import sys,struct; assert sys.version_info[:2]==(3,10) and struct.calcsize('P')==8, 'Python 3.10 x64 required'"
if ($LASTEXITCODE -ne 0) { throw 'Python 3.10 x64 required.' }
& $pythonExe -m pip install -r (Join-Path $project 'requirements-native.txt') cmake==4.4.4 ninja==1.13.2 $project
if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed.' }
$options = @('--runtime', $Runtime, '--device-name', $DeviceName)
if ($Cache) { $options += @('--cache', [IO.Path]::GetFullPath($Cache)) }
if ($BuildOnly) { $options += '--build-only' }
& $pythonExe (Join-Path $PSScriptRoot 'setup_native.py') @options
if ($LASTEXITCODE -ne 0) { throw 'Native setup failed; see the error above. Re-running reuses verified downloads.' }
Write-Host "Native runtime: $Runtime"
Write-Host "Python: $pythonExe"
Write-Host 'No plugin was changed. Follow docs/DEPLOY_NATIVE.md to preview and connect Coopanion.'
