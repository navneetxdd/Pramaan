# Pramaan

**Pramaan** is a multi-vendor DVR/NVR forensic workstation for SIH26150 — acquisition, device identification, tiered recovery, chain-of-custody, and PAdES-signed reporting.

## Repository layout

```
/src              React UI (Vite + TypeScript)
/src-tauri        Tauri v2 desktop shell
/engine           Python FastAPI forensic engine (sidecar)
/run.py           Backend-only dev launcher (API testing — not the application)
/DESIGN.md        UI/UX specification (Part K)
/DEVIATIONS.md    Spec gap log
```

## Development

### Desktop app (SAC-safe on Windows)

Windows Smart App Control blocks local `tauri build`. Install a **Desktop shortcut with the Pramaan icon** (one-time setup):

```powershell
powershell -ExecutionPolicy Bypass -File scripts/install-pramaan-desktop.ps1
```

Then double-click **Pramaan** on your Desktop — launches WebView2 UI + forensic engine with no console window.

For a full Tauri NSIS/MSI installer, push to GitHub and download the `pramaan-windows-release` artifact (see [docs/DESKTOP.md](docs/DESKTOP.md)).

Alternative launcher:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/run-desktop-sac-safe.ps1
```

### Primary: Tauri desktop app

```bash
npm install
npm run tauri:dev
```

Starts the Vite dev server (port 5173), spawns the Python engine on `127.0.0.1:8787`, and opens the Tauri webview. API calls are proxied through Vite to `/api/v1/*`.

### Backend-only (curl / Postman / unit tests)

```bash
pip install -r engine/requirements.txt
python run.py
```

Engine listens on `http://127.0.0.1:8787`. This is **not** the application launch path — it does not serve the SPA.

### Frontend-only (browser against running engine)

```bash
python run.py          # terminal 1
npm run dev            # terminal 2 → http://localhost:5173
```

## API

All clients use **`/api/v1/*`** only. Version and capabilities: `GET /api/v1/version`.

## Documentation

- [Release documentation index](docs/README.md)
- [SIH26150 release audit](docs/SIH26150-AUDIT.md)
- [Architecture and trust boundaries](docs/ARCHITECTURE.md)
- [OEM capabilities and limitations](docs/CAPABILITIES-AND-LIMITATIONS.md)
- [Operations procedures](docs/OPERATIONS-SOP.md)
- [User manual](docs/USER-MANUAL.md)
- [Validation report](docs/VALIDATION-REPORT.md)
- [Release checklist](docs/RELEASE-CHECKLIST.md)

## Version bump

```bash
npm run version:bump -- 0.3.0
```

Updates `engine/app/__init__.py`, `package.json`, and `src-tauri/tauri.conf.json` together.

## Tests

```bash
python -m pytest engine/tests -q
npm run build
python scripts/smoke_test.py
```

## Data locations

- Application DB: `~/ForensicWorkstation/data/forensic.db` (override: `FORENSIC_WORKSTATION_DATA`)
- Case artifacts: under per-case directories referenced from the DB
