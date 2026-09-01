[CmdletBinding()]
param(
    [string]$Python = "python",
    [string]$TargetTriple,
    [switch]$SkipEngine,
    [switch]$SkipDependencyInstall
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "../..")).Path

if ($env:OS -ne "Windows_NT") {
    throw "Windows desktop packages must be built on Windows."
}

if (-not $TargetTriple) {
    $TargetTriple = (& rustc --print host-tuple).Trim()
    if ($LASTEXITCODE -ne 0 -or -not $TargetTriple) {
        throw "rustc could not determine the Windows target triple."
    }
}

if (-not $SkipEngine) {
    $engineArguments = @{
        Python = $Python
        TargetTriple = $TargetTriple
        SkipDependencyInstall = $SkipDependencyInstall
    }
    & (Join-Path $PSScriptRoot "build-engine.ps1") @engineArguments
}

$SidecarPath = Join-Path $ProjectRoot "src-tauri\binaries\pramaan-engine-$TargetTriple.exe"
if (-not (Test-Path -LiteralPath $SidecarPath -PathType Leaf)) {
    throw "The Tauri sidecar is missing: $SidecarPath"
}

Push-Location $ProjectRoot
try {
    if (-not $SkipDependencyInstall) {
        & npm.cmd ci
        if ($LASTEXITCODE -ne 0) {
            throw "npm ci failed."
        }
    }

    & npm.cmd exec -- tauri build -- --locked
    if ($LASTEXITCODE -ne 0) {
        throw "The Tauri Windows package build failed."
    }
} finally {
    Pop-Location
}

$BundleRoot = Join-Path $ProjectRoot "src-tauri\target\release\bundle"
if (-not (Test-Path -LiteralPath $BundleRoot -PathType Container)) {
    throw "Tauri completed without creating the release bundle directory."
}

Get-ChildItem -LiteralPath $BundleRoot -Recurse -File |
    Where-Object { $_.Extension -in ".exe", ".msi" } |
    Sort-Object FullName |
    ForEach-Object { Write-Output $_.FullName }
