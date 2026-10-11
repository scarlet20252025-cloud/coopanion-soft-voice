param([string]$Python='python')
$ErrorActionPreference='Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
& $Python -m unittest discover -s tests
if ($LASTEXITCODE -ne 0) {throw 'Tests failed'}
& $Python -m build
if ($LASTEXITCODE -ne 0) {throw 'Build failed'}
