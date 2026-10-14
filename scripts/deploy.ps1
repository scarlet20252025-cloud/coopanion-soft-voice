param(
    [string]$Runtime,
    [string]$CoopanionRoot,
    [string]$BotId='companion',
    [string]$DeviceName,
    [switch]$RuntimeOnly,
    [switch]$NoLaunch,
    [switch]$NoEnableSpeech
)
$ErrorActionPreference='Stop'
$project=Split-Path $PSScriptRoot -Parent
$release=Get-Content -LiteralPath (Join-Path $project 'portable-release.json') -Raw | ConvertFrom-Json
if (-not $Runtime) { $Runtime=Join-Path $project ('.runtime-portable/'+$release.version) }
$Runtime=[IO.Path]::GetFullPath($Runtime)
if ($Runtime -match '[^\x00-\x7F]') { throw 'Choose an English installation path with -Runtime.' }
$marker=Join-Path $Runtime 'portable-manifest.json'
if (-not (Test-Path -LiteralPath $marker)) {
    $archive=$Runtime+'.download.zip'
    New-Item -ItemType Directory -Force (Split-Path $Runtime -Parent) | Out-Null
    if (-not (Test-Path -LiteralPath $archive) -or (Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash -ne $release.sha256) {
        Write-Host ('Downloading offline model bundle ('+[Math]::Round($release.bytes/1MB)+' MiB) | Asryto')
        $partial=$archive+'.partial'
        $savedProgress=$ProgressPreference;$ProgressPreference='SilentlyContinue'
        try { Invoke-WebRequest -Uri $release.url -OutFile $partial -UseBasicParsing }
        finally { $ProgressPreference=$savedProgress }
        if ((Get-FileHash -LiteralPath $partial -Algorithm SHA256).Hash -ne $release.sha256) { throw 'Bundle checksum mismatch; do not install.' }
        Move-Item -LiteralPath $partial -Destination $archive -Force
    }
    Write-Host 'Extracting verified offline bundle...'
    Expand-Archive -LiteralPath $archive -DestinationPath $Runtime -Force
}
if ((Get-Content -LiteralPath $marker -Raw | ConvertFrom-Json).version -ne $release.version) { throw 'Unexpected installed bundle version; use a new -Runtime directory.' }
$installOptions=@{BotId=$BotId}
if ($CoopanionRoot) { $installOptions.CoopanionRoot=$CoopanionRoot }
if ($DeviceName) { $installOptions.DeviceName=$DeviceName }
foreach ($flag in @('RuntimeOnly','NoLaunch','NoEnableSpeech')) { if ((Get-Variable $flag -ValueOnly)) { $installOptions[$flag]=$true } }
& (Join-Path $Runtime 'scripts/install-portable.ps1') @installOptions
