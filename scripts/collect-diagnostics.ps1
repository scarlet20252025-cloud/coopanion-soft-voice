param([string]$Runtime,[string]$CoopanionRoot,[string]$BotId='companion',[string]$OutputDirectory,[int]$Seconds=0,[int]$Interval=2)
$ErrorActionPreference='Stop'
$voiceBase=Split-Path $PSScriptRoot -Parent
$voicePython=$null;$voiceData=$null
if (-not $CoopanionRoot) {
    . (Join-Path $PSScriptRoot 'find-coopanion.ps1')
    $voiceCandidates=@(Find-CoopanionDirectory)
    if ($voiceCandidates.Count -eq 1) {$CoopanionRoot=$voiceCandidates[0]}
}
if ($CoopanionRoot) {
    $voiceData=Join-Path $CoopanionRoot ('data/home/'+$BotId+'/data/soft-voice')
    $voiceProfileFile=Join-Path $voiceData 'runtime-profile.json'
    if (Test-Path -LiteralPath $voiceProfileFile) {
        $voiceProfile=Get-Content -LiteralPath $voiceProfileFile -Raw -Encoding UTF8 | ConvertFrom-Json
        if (-not $Runtime) {
            $Runtime=$voiceProfile.runtime
            if (-not [IO.Path]::IsPathRooted($Runtime)) {$Runtime=Join-Path $voiceData $Runtime}
        }
        $voicePython=$voiceProfile.python
        if (-not [IO.Path]::IsPathRooted($voicePython)) {$voicePython=Join-Path $voiceData $voicePython}
    }
}
if (-not $Runtime -and (Test-Path -LiteralPath (Join-Path $voiceBase 'python/python.exe'))) {$Runtime=$voiceBase}
if ($Runtime -and (Test-Path -LiteralPath (Join-Path $Runtime 'python/python.exe'))) {$voicePython=Join-Path $Runtime 'python/python.exe'}
if (-not $Runtime -or -not $voicePython) {
    Add-Type -AssemblyName System.Windows.Forms
    $voicePicker=New-Object System.Windows.Forms.FolderBrowserDialog
    $voicePicker.Description='Select the voice runtime directory containing python/python.exe'
    if ($voicePicker.ShowDialog() -ne [System.Windows.Forms.DialogResult]::OK) {throw 'No voice runtime selected.'}
    $Runtime=$voicePicker.SelectedPath;$voicePython=Join-Path $Runtime 'python/python.exe'
}
if (-not (Test-Path -LiteralPath $voicePython -PathType Leaf)) {throw 'Portable Python not found. Select the complete voice runtime folder.'}
if (-not $OutputDirectory) {$OutputDirectory=Join-Path $voiceBase 'diagnostics'}
$voiceArgs=@('--runtime',$Runtime,'--output',$OutputDirectory,'--seconds',[string]$Seconds,'--interval',[string]$Interval)
if ($voiceData) {$voiceArgs+=@('--data-dir',$voiceData)}
$env:PYTHONUTF8='1'
Write-Host 'Asryto voice diagnostics: no inference, no chat/config dump, no automatic upload.'
Write-Host ('Monitoring seconds: '+$Seconds+'; output: '+$OutputDirectory)
$voiceStandalone=Join-Path $PSScriptRoot 'collect_diagnostics.py'
if (-not (Test-Path -LiteralPath $voiceStandalone)) {$voiceStandalone=Join-Path $voiceBase 'src/coopanion_soft_voice/diagnostics.py'}
if (Test-Path -LiteralPath $voiceStandalone) {& $voicePython $voiceStandalone @voiceArgs}
else {& $voicePython -m coopanion_soft_voice.diagnostics @voiceArgs}
if ($LASTEXITCODE -ne 0) {throw 'Diagnostics failed. Keep the final error message.'}
