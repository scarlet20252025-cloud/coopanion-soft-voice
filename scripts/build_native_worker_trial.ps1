param(
    [Parameter(Mandatory=$true)][string]$QwenSource,
    [Parameter(Mandatory=$true)][string]$Compiler,
    [string]$Output=(Join-Path $PSScriptRoot '../.runtime/native-worker-trial-build')
)
$ErrorActionPreference='Stop'
$revision=& git -C $QwenSource rev-parse HEAD
if($LASTEXITCODE -ne 0 -or $revision -ne '51512f129a7419567f4b8abfb06801451789b8f1'){throw 'Use the pinned qwentts.cpp source from docs/DEPLOY_NATIVE.md.'}
$header=Join-Path $QwenSource 'src/qwen.h'
if(-not (Test-Path -LiteralPath $header)){throw 'Pinned public ABI header is missing'}
New-Item -ItemType Directory -Path $Output -Force | Out-Null
$Output=(Resolve-Path -LiteralPath $Output).Path
$json=Join-Path $Output 'json.hpp'
if(-not (Test-Path -LiteralPath $json)){
    Invoke-WebRequest -Uri 'https://raw.githubusercontent.com/nlohmann/json/v3.11.3/single_include/nlohmann/json.hpp' -OutFile $json
}
if((Get-FileHash -LiteralPath $json -Algorithm SHA256).Hash.ToLowerInvariant() -ne '9bea4c8066ef4a1c206b2be5a36302f8926f7fdc6087af5d20b417d0cf103ea6'){throw 'JSON header SHA256 mismatch'}
$source=Join-Path $PSScriptRoot '../native/voice_worker_trial.cpp'
$exe=Join-Path $Output 'voice-worker.exe'
& $Compiler -std=c++17 -O2 -static -Wno-deprecated-declarations -I (Join-Path $QwenSource 'src') -I $Output $source -o $exe -lbcrypt -lpsapi -lwinmm
if($LASTEXITCODE -ne 0){throw 'Experimental worker build failed'}
Copy-Item -LiteralPath (Join-Path $PSScriptRoot '../native/THIRD_PARTY_NOTICES.md') -Destination $Output
& $exe --about
if($LASTEXITCODE -ne 0){throw 'Worker smoke test failed'}
Write-Host 'Experimental buffered-only worker built. It has NOT been installed or selected in Coopanion.'
