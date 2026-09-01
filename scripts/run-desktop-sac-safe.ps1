# SAC-safe desktop launch (no Rust release build required)
#
# Windows Smart App Control blocks unsigned proc-macros during `tauri build`.
# Use one of these free paths instead:

[CmdletBinding()]
param(
    [ValidateSet("browser", "webview", "tauri-dev", "help")]
    [string]$Mode = "webview"
)

$ErrorActionPreference = "Stop"
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $ProjectRoot

function Test-EngineReady {
    try {
        $version = Invoke-RestMethod "http://127.0.0.1:8787/api/v1/version" -TimeoutSec 2
        return $version.status -eq "ok"
    } catch {
        return $false
    }
}

function Start-EngineIfNeeded {
    if (Test-EngineReady) {
        Write-Host "Engine already running on http://127.0.0.1:8787"
        return
    }
    Write-Host "Starting forensic engine..."
    Start-Process -FilePath "python" -ArgumentList "run.py" -WorkingDirectory $ProjectRoot -WindowStyle Hidden
    foreach ($attempt in 1..40) {
        if (Test-EngineReady) {
            Write-Host "Engine ready."
            return
        }
        Start-Sleep -Milliseconds 500
    }
    throw "Engine failed to start on port 8787."
}

switch ($Mode) {
    "browser" {
        Start-EngineIfNeeded
        if (-not (Test-Path "dist/index.html")) {
            Write-Host "Building frontend..."
            npm run build
        }
        Write-Host "Starting static UI on http://127.0.0.1:5174"
        Start-Process -FilePath "python" -ArgumentList "-m", "http.server", "5174", "--directory", "dist" -WorkingDirectory $ProjectRoot -WindowStyle Hidden
        Start-Sleep -Seconds 1
        Start-Process "http://127.0.0.1:5174"
        Write-Host "Open Pramaan in your browser. Engine API: http://127.0.0.1:8787"
    }
    "webview" {
        if (-not (Test-Path "dist/index.html")) {
            Write-Host "Building frontend..."
            npm run build
        }
        Write-Host "Launching pywebview shell (production UI + engine sidecar)..."
        python desktop.py --production
    }
    "tauri-dev" {
        Write-Host "Attempting Tauri DEV mode (debug Rust — may still be blocked by SAC on some hosts)..."
        npm run tauri:dev
    }
    "help" {
        Write-Host @"

SAC workaround options (free):

1. webview  (default) — python desktop.py --production
   Native window via WebView2. No Rust compile. Full UI + engine.

2. browser — static dist/ + system browser
   Same functionality; looks less like a desktop app.

3. tauri-dev — npm run tauri:dev
   Debug builds sometimes pass SAC where release builds fail. Not guaranteed.

4. CI installer — push to GitHub; download artifact from Actions:
   gh run list --workflow=ci.yml
   gh run download <run-id> -n pramaan-windows-release

5. install — one-time Desktop shortcut with icon (recommended on SAC hosts):
   powershell -ExecutionPolicy Bypass -File scripts/install-pramaan-desktop.ps1

Release installers are built on windows-latest in GitHub Actions (no local SAC).

"@
    }
}
