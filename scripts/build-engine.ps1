[CmdletBinding()]
param(
    [string]$Python = "python",
    [string]$TargetTriple,
    [switch]$SkipDependencyInstall
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$SpecPath = Join-Path $ProjectRoot "engine\pyinstaller.spec"
$BuildRoot = Join-Path $ProjectRoot "artifacts\pyinstaller"
$DistRoot = Join-Path $BuildRoot "dist"
$WorkRoot = Join-Path $BuildRoot "work"
$VenvRoot = Join-Path $BuildRoot "venv"
$BinaryRoot = Join-Path $ProjectRoot "src-tauri\binaries"

if ($env:OS -ne "Windows_NT") {
    throw "The Pramaan release sidecar must be built on Windows."
}

if (-not $TargetTriple) {
    $TargetTriple = (& rustc --print host-tuple).Trim()
    if ($LASTEXITCODE -ne 0 -or -not $TargetTriple) {
        throw "rustc could not determine the Windows target triple."
    }
}

if ($TargetTriple -notmatch "-windows-msvc$") {
    throw "Unsupported release target '$TargetTriple'. Use a Windows MSVC target."
}

if (-not $env:SOURCE_DATE_EPOCH) {
    $commitEpoch = (& git -C $ProjectRoot log -1 --format=%ct 2>$null).Trim()
    $env:SOURCE_DATE_EPOCH = if ($commitEpoch -match "^\d+$") { $commitEpoch } else { "1704067200" }
}
$env:PYTHONHASHSEED = "0"

Remove-Item -LiteralPath $BuildRoot -Recurse -Force -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Path $BuildRoot, $DistRoot, $WorkRoot, $BinaryRoot -Force | Out-Null

if (-not $SkipDependencyInstall) {
    & $Python -m venv $VenvRoot
    if ($LASTEXITCODE -ne 0) {
        throw "Creating the isolated packaging environment failed."
    }
    $BuildPython = Join-Path $VenvRoot "Scripts\python.exe"

    & $BuildPython -m pip install --disable-pip-version-check --requirement (Join-Path $ProjectRoot "engine\requirements.txt")
    if ($LASTEXITCODE -ne 0) {
        throw "Installing engine dependencies failed."
    }
    & $BuildPython -m pip install --disable-pip-version-check --requirement (Join-Path $ProjectRoot "engine\requirements-build.txt")
    if ($LASTEXITCODE -ne 0) {
        throw "Installing packaging dependencies failed."
    }
} else {
    $BuildPython = $Python
}

& $BuildPython -m PyInstaller `
    --noconfirm `
    --clean `
    --distpath $DistRoot `
    --workpath $WorkRoot `
    $SpecPath
if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller failed to create the Pramaan engine."
}

$BuiltBinary = Join-Path $DistRoot "pramaan-engine.exe"
if (-not (Test-Path -LiteralPath $BuiltBinary -PathType Leaf)) {
    throw "PyInstaller completed without producing $BuiltBinary."
}

Get-ChildItem -LiteralPath $BinaryRoot -Filter "pramaan-engine-*.exe" -File |
    Remove-Item -Force

$SidecarPath = Join-Path $BinaryRoot "pramaan-engine-$TargetTriple.exe"
Copy-Item -LiteralPath $BuiltBinary -Destination $SidecarPath -Force

$Hash = (Get-FileHash -LiteralPath $SidecarPath -Algorithm SHA256).Hash.ToLowerInvariant()
Set-Content -LiteralPath "$SidecarPath.sha256" -Value "$Hash  $(Split-Path $SidecarPath -Leaf)" -Encoding ascii

Write-Output $SidecarPath
