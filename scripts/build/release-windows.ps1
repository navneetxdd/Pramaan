[CmdletBinding()]
param(
    [string]$Python = "python",
    [string]$TargetTriple,
    [switch]$SkipDependencyInstall
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "../..")).Path

if (-not $TargetTriple) {
    $TargetTriple = (& rustc --print host-tuple).Trim()
    if ($LASTEXITCODE -ne 0 -or -not $TargetTriple) {
        throw "rustc could not determine the Windows target triple."
    }
}

$EngineArguments = @{
    Python = $Python
    TargetTriple = $TargetTriple
    SkipDependencyInstall = $SkipDependencyInstall
}
$SidecarPath = & (Join-Path $PSScriptRoot "build-engine.ps1") @EngineArguments |
    Select-Object -Last 1
if (-not (Test-Path -LiteralPath $SidecarPath -PathType Leaf)) {
    throw "The engine build did not return a valid sidecar path."
}

& (Join-Path $PSScriptRoot "sign-windows.ps1") -Paths $SidecarPath
$SidecarHash = (Get-FileHash -LiteralPath $SidecarPath -Algorithm SHA256).Hash.ToLowerInvariant()
Set-Content `
    -LiteralPath "$SidecarPath.sha256" `
    -Value "$SidecarHash  $(Split-Path $SidecarPath -Leaf)" `
    -Encoding ascii

$DesktopArguments = @{
    Python = $Python
    TargetTriple = $TargetTriple
    SkipEngine = $true
    SkipDependencyInstall = $SkipDependencyInstall
}
& (Join-Path $PSScriptRoot "build-windows.ps1") @DesktopArguments

$ReleaseRoot = Join-Path $ProjectRoot "src-tauri\target\release"
$DesktopExecutable = Join-Path $ReleaseRoot "pramaan-desktop.exe"
$Installers = Get-ChildItem -LiteralPath (Join-Path $ReleaseRoot "bundle") -Recurse -File |
    Where-Object { $_.Extension -in ".exe", ".msi" } |
    Sort-Object FullName

$SignTargets = @($DesktopExecutable) + @($Installers.FullName)
& (Join-Path $PSScriptRoot "sign-windows.ps1") -Paths $SignTargets

$ArtifactRoot = Join-Path $ProjectRoot "artifacts\windows"
Remove-Item -LiteralPath $ArtifactRoot -Recurse -Force -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Path $ArtifactRoot -Force | Out-Null

$ReleasedFiles = foreach ($Installer in $Installers) {
    $Destination = Join-Path $ArtifactRoot $Installer.Name
    Copy-Item -LiteralPath $Installer.FullName -Destination $Destination -Force
    Get-Item -LiteralPath $Destination
}

$ChecksumLines = $ReleasedFiles |
    Sort-Object Name |
    ForEach-Object {
        $Hash = (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
        "$Hash  $($_.Name)"
    }
Set-Content -LiteralPath (Join-Path $ArtifactRoot "SHA256SUMS.txt") -Value $ChecksumLines -Encoding ascii

Write-Output $ArtifactRoot
