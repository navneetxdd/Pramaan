[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string[]]$Paths,
    [string]$TimestampUrl = "http://timestamp.digicert.com"
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$CertificateBase64 = $env:WINDOWS_CERTIFICATE_BASE64
$CertificatePassword = $env:WINDOWS_CERTIFICATE_PASSWORD

if (-not $CertificateBase64 -and -not $CertificatePassword) {
    Write-Output "Authenticode secrets are not configured; artifacts remain unsigned."
    exit 0
}
if (-not $CertificateBase64 -or -not $CertificatePassword) {
    throw "Both WINDOWS_CERTIFICATE_BASE64 and WINDOWS_CERTIFICATE_PASSWORD are required for signing."
}

$SignToolCommand = Get-Command signtool.exe -ErrorAction SilentlyContinue
if ($SignToolCommand) {
    $SignTool = $SignToolCommand.Source
} else {
    $KitsRoot = "${env:ProgramFiles(x86)}\Windows Kits\10\bin"
    $SignTool = Get-ChildItem -Path "$KitsRoot\*\x64\signtool.exe" -File -ErrorAction SilentlyContinue |
        Sort-Object FullName -Descending |
        Select-Object -First 1 -ExpandProperty FullName
}
if (-not $SignTool) {
    throw "signtool.exe was not found. Install the Windows SDK signing tools."
}

$ResolvedPaths = $Paths |
    ForEach-Object { Resolve-Path -LiteralPath $_ -ErrorAction Stop } |
    ForEach-Object { $_.Path } |
    Sort-Object -Unique
if (-not $ResolvedPaths) {
    throw "No files were supplied for Authenticode signing."
}

$PfxPath = Join-Path ([System.IO.Path]::GetTempPath()) ("pramaan-signing-{0}.pfx" -f [guid]::NewGuid())
$ImportedCertificate = $null
$CertificateExisted = $false

try {
    [System.IO.File]::WriteAllBytes($PfxPath, [Convert]::FromBase64String($CertificateBase64))
    $SecurePassword = ConvertTo-SecureString $CertificatePassword -AsPlainText -Force

    $Pfx = [System.Security.Cryptography.X509Certificates.X509Certificate2]::new(
        $PfxPath,
        $CertificatePassword,
        [System.Security.Cryptography.X509Certificates.X509KeyStorageFlags]::EphemeralKeySet
    )
    $Thumbprint = $Pfx.Thumbprint
    $ExistingCertificate = Get-Item "Cert:\CurrentUser\My\$Thumbprint" -ErrorAction SilentlyContinue
    $CertificateExisted = $null -ne $ExistingCertificate
    if (-not $CertificateExisted) {
        $ImportedCertificate = Import-PfxCertificate `
            -FilePath $PfxPath `
            -CertStoreLocation "Cert:\CurrentUser\My" `
            -Password $SecurePassword `
            -Exportable:$false
    }

    foreach ($Path in $ResolvedPaths) {
        & $SignTool sign `
            /sha1 $Thumbprint `
            /s My `
            /fd SHA256 `
            /tr $TimestampUrl `
            /td SHA256 `
            $Path
        if ($LASTEXITCODE -ne 0) {
            throw "Authenticode signing failed for $Path."
        }

        & $SignTool verify /pa /all $Path
        if ($LASTEXITCODE -ne 0) {
            throw "Authenticode verification failed for $Path."
        }
    }
} finally {
    if ($ImportedCertificate -and -not $CertificateExisted) {
        Remove-Item -LiteralPath "Cert:\CurrentUser\My\$($ImportedCertificate.Thumbprint)" -Force -ErrorAction SilentlyContinue
    }
    Remove-Item -LiteralPath $PfxPath -Force -ErrorAction SilentlyContinue
    $CertificateBase64 = $null
    $CertificatePassword = $null
    $SecurePassword = $null
}
