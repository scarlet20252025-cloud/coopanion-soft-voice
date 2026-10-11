param([string]$Python='py', [string]$Runtime, [switch]$SkipModelDownload)
$ErrorActionPreference='Stop'
$taskProject=Split-Path $PSScriptRoot -Parent
if (-not $Runtime) {$Runtime=Join-Path $taskProject '.runtime'}
Set-Location $taskProject
if (-not (Test-Path '.venv/Scripts/python.exe')) {
    if ($Python -eq 'py') { & py -3.10 -m venv .venv } else { & $Python -m venv .venv }
    if ($LASTEXITCODE -ne 0) {throw 'Python 3.10 is required.'}
}
$taskPython=Join-Path $taskProject '.venv/Scripts/python.exe'
& $taskPython -m pip install 'pip==25.0.1' 'build==1.2.2.post1'
if ($LASTEXITCODE -ne 0) {throw 'pip bootstrap failed'}
& $taskPython -m pip install 'torch==2.3.1' 'torchaudio==2.3.1' --index-url https://download.pytorch.org/whl/cu121
if ($LASTEXITCODE -ne 0) {throw 'CUDA torch installation failed'}
& $taskPython -m pip install -r requirements-runtime.txt -c requirements-runtime.lock
if ($LASTEXITCODE -ne 0) {throw 'Runtime dependency installation failed'}
# Qwen's top-level dependency list includes its optional Gradio demo. This
# package uses inference only; its imports are covered by requirements-runtime.
& $taskPython -m pip install --no-deps 'qwen-tts==0.1.1' .
if ($LASTEXITCODE -ne 0) {throw 'Project installation failed'}
if (-not $SkipModelDownload) {
    & $taskPython -m coopanion_soft_voice.cli --runtime $Runtime download
    if ($LASTEXITCODE -ne 0) {throw 'Model download or checksum verification failed'}
}
& $taskPython -m coopanion_soft_voice.cli --runtime $Runtime doctor
if ($LASTEXITCODE -ne 0) {throw 'Preflight failed; resolve it before enabling speech'}
Write-Host 'Ready. See README.md for speech and Coopanion installation commands.'
