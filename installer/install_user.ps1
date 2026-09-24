# ParqBench Non-Admin User Installer
# Installs to %LOCALAPPDATA%\Programs\ParqBench without requiring Administrator rights.

$ErrorActionPreference = "Stop"

$AppName = "ParqBench"
$TargetDir = "$env:LOCALAPPDATA\Programs\$AppName"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
$SourceDir = Join-Path (Split-Path -Parent $ScriptDir) "dist\ParqBench"

if (-not (Test-Path $SourceDir)) {
    # Check if run from within portable folder
    if (Test-Path (Join-Path $ScriptDir "ParqBench.exe")) {
        $SourceDir = $ScriptDir
    } else {
        Write-Error "Could not find ParqBench build files. Please build the application first (python build_release.py)."
        exit 1
    }
}

Write-Host "Installing $AppName to $TargetDir (Current User)..." -ForegroundColor Cyan

# 1. Create Target Directory
if (-not (Test-Path $TargetDir)) {
    New-Item -ItemType Directory -Path $TargetDir -Force | Out-Null
}

# 2. Copy Application Files
Copy-Item -Path "$SourceDir\*" -Destination $TargetDir -Recurse -Force
Write-Host "Files copied successfully." -ForegroundColor Green

$ExePath = Join-Path $TargetDir "ParqBench.exe"
$IconPath = Join-Path $TargetDir "assets\icon.ico"
if (-not (Test-Path $IconPath)) { $IconPath = $ExePath }

# 3. Create Start Menu Shortcut
$WshShell = New-Object -ComObject WScript.Shell
$StartMenuDir = "$env:APPDATA\Microsoft\Windows\Start Menu\Programs"
$ShortcutPath = Join-Path $StartMenuDir "$AppName.lnk"

$Shortcut = $WshShell.CreateShortcut($ShortcutPath)
$Shortcut.TargetPath = $ExePath
$Shortcut.WorkingDirectory = $TargetDir
$Shortcut.IconLocation = $IconPath
$Shortcut.Description = "ParqBench — Parquet Tabular Suite"
$Shortcut.Save()
Write-Host "Start Menu shortcut created: $ShortcutPath" -ForegroundColor Green

# 4. Create Desktop Shortcut
$DesktopDir = [Environment]::GetFolderPath("Desktop")
$DesktopShortcutPath = Join-Path $DesktopDir "$AppName.lnk"
$DesktopShortcut = $WshShell.CreateShortcut($DesktopShortcutPath)
$DesktopShortcut.TargetPath = $ExePath
$DesktopShortcut.WorkingDirectory = $TargetDir
$DesktopShortcut.IconLocation = $IconPath
$DesktopShortcut.Description = "ParqBench — Parquet Tabular Suite"
$DesktopShortcut.Save()
Write-Host "Desktop shortcut created: $DesktopShortcutPath" -ForegroundColor Green

# 5. Register .parquet file association under HKCU (No admin required)
try {
    $ProgId = "ParqBench.ParquetFile"
    New-Item -Path "HKCU:\Software\Classes\.parquet" -Value $ProgId -Force | Out-Null
    New-Item -Path "HKCU:\Software\Classes\$ProgId" -Value "Apache Parquet File" -Force | Out-Null
    New-Item -Path "HKCU:\Software\Classes\$ProgId\DefaultIcon" -Value "$IconPath,0" -Force | Out-Null
    New-Item -Path "HKCU:\Software\Classes\$ProgId\shell\open\command" -Value "`"$ExePath`" `"%1`"" -Force | Out-Null
    Write-Host "File association for .parquet registered." -ForegroundColor Green
} catch {
    Write-Warning "Could not register file association: $_"
}

Write-Host "`n$AppName installed successfully! You can launch it from your Start Menu or Desktop." -ForegroundColor Cyan
