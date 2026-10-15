param([string]$Runtime, [string]$Device, [switch]$NoPause, [switch]$PreflightOnly, [switch]$DiscoverOnly)
$ErrorActionPreference='Stop'
[Console]::OutputEncoding=[System.Text.UTF8Encoding]::new($false)
$env:PYTHONUTF8='1';$env:PYTHONIOENCODING='utf-8'
$kit=Split-Path $PSScriptRoot -Parent
$exitCode=1
function Get-VoiceRuntimes {
    $found=New-Object 'System.Collections.Generic.List[string]'
    if ($Runtime) { $found.Add($Runtime) }
    else {
        $found.Add($kit);$found.Add((Split-Path $kit -Parent))
        $BotId='companion'
        . (Join-Path $PSScriptRoot 'find-coopanion.ps1')
        $apps=@(Find-CoopanionDirectory)
        # Also cover an initialized non-default Bot in a running desktop.
        $apps+=@(Get-CimInstance Win32_Process -Filter "Name='Coopanion.exe'" -ErrorAction SilentlyContinue |
            Where-Object ExecutablePath | ForEach-Object { Split-Path $_.ExecutablePath -Parent })
        foreach ($app in ($apps | Sort-Object -Unique)) {
            $homes=Join-Path $app 'data/home'
            if (Test-Path -LiteralPath $homes) {
                Get-ChildItem -LiteralPath $homes -Directory -ErrorAction SilentlyContinue | ForEach-Object {
                    $profile=Join-Path $_.FullName 'data/soft-voice/runtime-profile.json'
                    if (Test-Path -LiteralPath $profile) {
                        try { $value=Get-Content -LiteralPath $profile -Raw | ConvertFrom-Json
                            if ($value.runtime) { $found.Add([string]$value.runtime) }
                        } catch { }
                    }
                }
            }
        }
    }
    $found | Where-Object {
        (Test-Path -LiteralPath (Join-Path $_ 'native-runtime.json') -PathType Leaf) -and
        (Test-Path -LiteralPath (Join-Path $_ 'python/python.exe') -PathType Leaf)
    } | ForEach-Object { [IO.Path]::GetFullPath($_).TrimEnd('\') } | Sort-Object -Unique
}
try {
    Write-Host '轻核语音 · Intel 核显一键对照工具 1.0.0 | Asryto' -ForegroundColor Cyan
    Write-Host '复用已安装模型，无需下载；不修改桌宠设置，不自动上传。'
    Write-Host '[1/3] 正在查找语音安装目录……'
    $paths=@(Get-VoiceRuntimes)
    if ($DiscoverOnly) { $paths | ConvertTo-Json; exit 0 }
    if ($paths.Count -eq 1) { $Runtime=$paths[0] }
    elseif ($paths.Count -gt 1 -and -not $NoPause) {
        Write-Host '检测到多个安装，请输入正在使用的序号：'
        for ($i=0;$i -lt $paths.Count;$i++) { Write-Host (('{0}. {1}' -f ($i+1),$paths[$i])) }
        $choice=Read-Host '序号';$number=0
        if (-not [int]::TryParse($choice,[ref]$number) -or $number -lt 1 -or $number -gt $paths.Count) { throw '未选择有效安装。' }
        $Runtime=$paths[$number-1]
    } elseif (-not $NoPause) {
        Write-Host '没有自动找到安装目录，请选择包含 native-runtime.json 的语音文件夹。'
        Add-Type -AssemblyName System.Windows.Forms
        $picker=New-Object System.Windows.Forms.FolderBrowserDialog
        $picker.Description='请选择包含 native-runtime.json 和 python 文件夹的语音安装目录'
        if ($picker.ShowDialog() -ne [System.Windows.Forms.DialogResult]::OK) { throw '已取消目录选择。' }
        $Runtime=$picker.SelectedPath
    } else { throw '无法唯一识别语音运行时，请传入 -Runtime。' }
    if (-not (Test-Path -LiteralPath (Join-Path $Runtime 'native-runtime.json'))) { throw '此目录不包含 native-runtime.json。' }
    $python=Join-Path $Runtime 'python/python.exe'
    if (-not (Test-Path -LiteralPath $python)) { throw '此目录没有随包 Python。请完成语音部署后重试。' }
    Write-Host ('已识别语音目录：'+$Runtime)
    if (-not $PreflightOnly) {
        # Avoid two resident models; never terminate the user's worker.
        do {
            $workers=@(Get-CimInstance Win32_Process -Filter "Name='python.exe'" -ErrorAction SilentlyContinue | Where-Object {
                $_.CommandLine -and $_.CommandLine.Contains($Runtime) -and $_.CommandLine -match 'coopanion_soft_voice.*\bworker\b|cache_worker|cache-worker'
            })
            if ($workers.Count) {
                if ($NoPause) { throw '语音工作进程仍在运行。请先在扩展中停止语音，再运行工具。' }
                Write-Host '请先在桌宠扩展中点击“停止语音”，避免重复加载模型。工具不会关闭你的程序。' -ForegroundColor Yellow
                [void](Read-Host '完成后按回车继续')
            }
        } while ($workers.Count)
    }
    Write-Host '[2/3] 检测核显并运行测试；每两秒更新当前阶段和已用时间。'
    $arguments=@((Join-Path $PSScriptRoot 'run_gpu_diagnostic.py'),'--runtime',$Runtime)
    if ($Device) { $arguments+=@('--device',$Device) }
    if ($PreflightOnly) { $arguments+='--preflight-only' }
    $started=Get-Date
    $ErrorActionPreference='Continue'
    & $python @arguments
    $exitCode=$LASTEXITCODE
    $ErrorActionPreference='Stop'
    $latest=Get-ChildItem -LiteralPath (Join-Path $kit 'reports') -Filter '*.zip' -ErrorAction SilentlyContinue | Where-Object { $_.LastWriteTime -ge $started } | Sort-Object LastWriteTime -Descending | Select-Object -First 1
    if (-not $latest) { throw 'Python 未能生成报告。请检查运行时依赖是否完整。' }
    Write-Host '[3/3] 日志打包结束。请回传 reports 文件夹内新生成的 ZIP。'
} catch {
    Write-Host ('无法开始：'+$_.Exception.Message) -ForegroundColor Yellow
    $reportRoot=Join-Path $kit 'reports'
    [void](New-Item -ItemType Directory -Force -Path $reportRoot)
    $zip=Join-Path $reportRoot ('startup-failure-'+(Get-Date -Format 'yyyyMMdd-HHmmss')+'.zip')
    Add-Type -AssemblyName System.IO.Compression
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $archive=[IO.Compression.ZipFile]::Open($zip,[IO.Compression.ZipArchiveMode]::Create)
    try {
        $message=$_.Exception.Message -replace '(?i)[a-z]:[\\/][^\r\n]*','[path]'
        $entry=$archive.CreateEntry('status.json');$writer=New-Object IO.StreamWriter($entry.Open())
        try { $writer.Write((@{success=$false;synthesisAttempted=$false;installedConfigurationModified=$false;stage='bootstrap';error=$message;toolVersion='1.0.0'} | ConvertTo-Json)) }
        finally { $writer.Dispose() }
    } finally { $archive.Dispose() }
    Write-Host ('故障报告：'+$zip)
}
if (-not $NoPause) { [void](Read-Host '按回车关闭窗口') }
exit $exitCode
