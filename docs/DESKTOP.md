# Pramaan desktop shell

## SAC / Windows Application Control

Local `npm run tauri:build` may fail with **Application Control policy blocked (os error 4551)** on freshly-linked Rust build-script `.exe` files and proc-macro DLLs. You cannot disable SAC on Windows 11 Home once enforcing is on — use a free alternative:

| Path | Command | SAC-safe? |
|------|---------|-----------|
| **pywebview (recommended)** | `powershell -File scripts/run-desktop-sac-safe.ps1 -Mode webview` | Yes |
| **Browser + engine** | `powershell -File scripts/run-desktop-sac-safe.ps1 -Mode browser` | Yes |
| **Tauri dev (debug)** | `powershell -File scripts/run-desktop-sac-safe.ps1 -Mode tauri-dev` | Usually |
| **WSL2 + cargo-xwin** | See [WSL2 release build](#wsl2-release-build-cargo-xwin) below | Yes (Linux host linker) |
| **CI installer** | Tag push or `workflow_dispatch` → download `pramaan-windows-release` artifact | Yes |

```powershell
# One-shot native desktop (builds UI if needed, starts engine + WebView2)
powershell -ExecutionPolicy Bypass -File scripts/run-desktop-sac-safe.ps1
```

Requires: `pip install -r requirements-desktop.txt` (pywebview + WebView2 runtime on Windows).

`src-tauri/Cargo.toml` keeps a `[profile.release.build-override]` block so proc-macros compile with `opt-level=0` — this fixes some SAC blocks locally but build-script executables may still be rejected.

### CI release installers

Push a version tag or run the workflow manually:

```bash
git tag v0.6.0
git push origin v0.6.0
```

Or: GitHub → Actions → **Pramaan CI** → **Run workflow**.

Download artifacts after the `windows-release` job completes:

```bash
gh run list --workflow=ci.yml --limit 5
gh run download <run-id> -n pramaan-windows-release -D ./release-artifacts
```

The job builds the PyInstaller sidecar, runs `tauri-apps/tauri-action` with `--bundles nsis,msi`, and uploads NSIS + MSI installers. Authenticode signing is not wired yet (TODO in workflow).

## WSL2 release build (cargo-xwin)

When SAC blocks `npx tauri build` on Windows but `npm run tauri dev` works, cross-compile from WSL2 so rustc never writes SAC-scanned host build scripts on the Windows volume during the link step.

### Prerequisites (Ubuntu on WSL2)

```bash
sudo apt update
sudo apt install -y clang llvm lld nsis
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh
source "$HOME/.cargo/env"
rustup target add x86_64-pc-windows-msvc
cargo install cargo-xwin
```

Also install Node.js 20+ and Python 3.11 in WSL (or use Windows Node/Python via `/mnt/c/...` — building the sidecar still requires Windows; run `scripts/build-engine.ps1` in PowerShell first, then build Tauri from WSL).

### Build flow

1. **Windows (PowerShell)** — freeze the engine sidecar (PyInstaller must run on Windows):

   ```powershell
   cd C:\Users\<you>\Desktop\SAH
   .\scripts\build-engine.ps1
   ```

2. **WSL2** — frontend + Tauri cross-compile:

   ```bash
   cd /mnt/c/Users/<you>/Desktop/SAH
   npm ci
   npm run build
   npm run tauri build -- --runner cargo-xwin --target x86_64-pc-windows-msvc --bundles nsis
   ```

Installers land in `src-tauri/target/x86_64-pc-windows-msvc/release/bundle/nsis/` (and `msi/` if you add `--bundles nsis,msi`).

## Tauri (when SAC allows or via CI / WSL2)

```bash
npm install
npm run tauri:dev    # development
npm run tauri:build  # release — often blocked locally by SAC
```

- **UI:** Vite dev server at `http://localhost:5173` (or bundled `dist/` in release builds)
- **Engine:** Python sidecar at `http://127.0.0.1:8787`
- **FFmpeg:** optional — app starts without it; a dismissible banner warns that MP4 export is unavailable

Config: `src-tauri/tauri.conf.json`

## Manual dev (browser)

```bash
python run.py          # terminal 1 — engine
npm run dev            # terminal 2 — UI at http://localhost:5173
```

## Layout

```
/src              React UI
/src-tauri        Tauri v2 shell
/engine           FastAPI forensic engine
/desktop.py       pywebview launcher (SAC-safe)
/scripts/run-desktop-sac-safe.ps1
```
