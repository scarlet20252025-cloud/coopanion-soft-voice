function Find-CoopanionDirectory {
    $candidates=New-Object 'System.Collections.Generic.List[string]'
    Get-CimInstance Win32_Process -Filter "Name='Coopanion.exe'" -ErrorAction SilentlyContinue | ForEach-Object {
        if ($_.ExecutablePath) { $candidates.Add((Split-Path $_.ExecutablePath -Parent)) }
    }
    foreach ($registry in @('HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\*','HKLM:\Software\Microsoft\Windows\CurrentVersion\Uninstall\*','HKLM:\Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\*')) {
        Get-ItemProperty -Path $registry -ErrorAction SilentlyContinue | Where-Object { $_.DisplayName -like '*Coopanion*' } | ForEach-Object {
            if ($_.InstallLocation) { $candidates.Add($_.InstallLocation) }
            if ($_.DisplayIcon) { $icon=($_.DisplayIcon -replace ',\d+$','').Trim('"');if ($icon -like '*Coopanion.exe') { $candidates.Add((Split-Path $icon -Parent)) } }
        }
    }
    $shortcutShell=New-Object -ComObject WScript.Shell
    try {
        foreach ($menu in @([Environment]::GetFolderPath('Desktop'),[Environment]::GetFolderPath('CommonDesktopDirectory'),[Environment]::GetFolderPath('StartMenu'),[Environment]::GetFolderPath('CommonStartMenu'))) {
            if ($menu -and (Test-Path -LiteralPath $menu)) {
                Get-ChildItem -LiteralPath $menu -Filter '*Coopanion*.lnk' -File -Recurse -ErrorAction SilentlyContinue | ForEach-Object {
                    $target=$shortcutShell.CreateShortcut($_.FullName).TargetPath
                    if ($target -like '*Coopanion.exe') { $candidates.Add((Split-Path $target -Parent)) }
                }
            }
        }
    } finally { [void][Runtime.InteropServices.Marshal]::ReleaseComObject($shortcutShell) }
    foreach ($base in @($env:LOCALAPPDATA,$env:ProgramFiles,${env:ProgramFiles(x86)},(Join-Path $env:LOCALAPPDATA 'Programs'))) {
        if ($base) { $candidates.Add((Join-Path $base 'Coopanion')) }
    }
    $candidates | Where-Object {
        (Test-Path -LiteralPath (Join-Path $_ 'Coopanion.exe') -PathType Leaf) -and
        (Test-Path -LiteralPath (Join-Path $_ 'data/extensions/package.json') -PathType Leaf) -and
        (Test-Path -LiteralPath (Join-Path $_ ('data/home/'+$BotId+'/config.json')) -PathType Leaf)
    } | ForEach-Object { [IO.Path]::GetFullPath($_).TrimEnd('\') } | Sort-Object -Unique
}
