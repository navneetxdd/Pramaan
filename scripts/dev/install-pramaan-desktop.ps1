# Creates Desktop + Start Menu shortcuts for Pramaan (SAC-safe pywebview shell).
# Double-click the shortcut to launch UI + engine with the Pramaan icon.

[CmdletBinding()]
param(
    [switch]$Launch,
    [switch]$SkipBuild
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "../..")).Path
$IconPath = Join-Path $ProjectRoot "src-tauri\icons\icon.ico"
$DesktopPy = Join-Path $ProjectRoot "desktop.py"
$LaunchArgs = ('"{0}" --production' -f $DesktopPy)

$PythonwCmd = Get-Command pythonw -ErrorAction SilentlyContinue
if ($PythonwCmd) {
    $Pythonw = $PythonwCmd.Source
} else {
    $PythonExe = (Get-Command python -ErrorAction Stop).Source
    $Pythonw = Join-Path (Split-Path $PythonExe -Parent) "pythonw.exe"
    if (-not (Test-Path -LiteralPath $Pythonw)) {
        throw "pythonw.exe not found. Install Python 3.11+ with the py launcher."
    }
}

if (-not (Test-Path -LiteralPath $IconPath)) {
    throw "Missing icon: $IconPath"
}

Set-Location $ProjectRoot

Write-Host "Installing Python dependencies..."
& python -m pip install --disable-pip-version-check -q `
    -r (Join-Path $ProjectRoot "engine\requirements.txt") `
    -r (Join-Path $ProjectRoot "requirements-desktop.txt")
if ($LASTEXITCODE -ne 0) {
    throw "Python dependency install failed."
}

if (-not $SkipBuild) {
    if (-not (Test-Path "node_modules")) {
        Write-Host "Installing npm dependencies..."
        npm ci
        if ($LASTEXITCODE -ne 0) { throw "npm ci failed." }
    }
    Write-Host "Building frontend..."
    npm run build
    if ($LASTEXITCODE -ne 0) { throw "npm run build failed." }
}

if (-not (Test-Path "dist\index.html")) {
    throw "dist/index.html missing. Run npm run build first."
}

function New-PramaanShortcut {
    param(
        [Parameter(Mandatory = $true)][string]$ShortcutPath
    )

    $WshShell = New-Object -ComObject WScript.Shell
    $Shortcut = $WshShell.CreateShortcut($ShortcutPath)
    $Shortcut.TargetPath = $Pythonw
    $Shortcut.Arguments = $LaunchArgs
    $Shortcut.WorkingDirectory = $ProjectRoot
    $Shortcut.IconLocation = "$IconPath,0"
    $Shortcut.Description = "Pramaan forensic workstation (UI + engine)"
    $Shortcut.WindowStyle = 7
    $Shortcut.Save()
}

$DesktopLink = Join-Path ([Environment]::GetFolderPath("Desktop")) "Pramaan.lnk"
$StartMenuDir = Join-Path ([Environment]::GetFolderPath("Programs")) "Pramaan"
New-Item -ItemType Directory -Force -Path $StartMenuDir | Out-Null
$StartMenuLink = Join-Path $StartMenuDir "Pramaan.lnk"

New-PramaanShortcut -ShortcutPath $DesktopLink
New-PramaanShortcut -ShortcutPath $StartMenuLink

Write-Host ""
Write-Host "Pramaan shortcuts created:"
Write-Host "  Desktop:    $DesktopLink"
Write-Host "  Start menu: $StartMenuLink"
Write-Host ""
Write-Host "Double-click Pramaan to launch the desktop app (WebView2 + forensic engine)."
Write-Host "For a signed Tauri installer, download the CI artifact (see README Desktop install)."

if ($Launch) {
    Start-Process -FilePath $Pythonw -ArgumentList $LaunchArgs -WorkingDirectory $ProjectRoot
}
