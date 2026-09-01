# Pramaan

Multi-vendor DVR/NVR forensic workstation for standardized acquisition, recovery, and analysis of surveillance evidence (SIH26150 / NTRO).

## Architecture

```
backend/pramaan/
  api/           REST endpoints (cases, acquire, recover, custody, export)
  core/          SQLite persistence, case registry, custody ledger
  recovery/      Vendor detector + pluggable adapters (Dahua DHAV, Hikvision HKVI, H.264 carve)
  analysis/      Segment export (FFmpeg) and case reporting
frontend/        React workstation UI (Cipher Margin design language)
```

## Requirements

- Python 3.11+
- Node.js 20+
- FFmpeg on `PATH` (optional; enables MP4 export from carved H.264)

## Quick start

```bash
# Backend
cd backend
python -m venv .venv
.venv\Scripts\activate   # Windows
pip install -r requirements.txt
cd ..
python run.py

# Frontend (dev)
cd frontend
npm install
npm run dev

# Production UI (served by FastAPI)
cd frontend && npm run build
python run.py
```

API: `http://127.0.0.1:8787` · Dev UI: `http://127.0.0.1:5173`

## Forensic workflow

1. **Cases** — open an investigation with examiner identity.
2. **Acquire** — ingest a disk image; SHA-256 hash recorded in custody.
3. **Recover** — vendor fingerprinting selects adapter; segments indexed by byte offset.
4. **Analyze** — review timeline, export segments (raw H.264 or MP4 via FFmpeg).
5. **Custody** — append-only audit trail for all actions.

## Tests

```bash
cd backend
pip install -r requirements.txt
pytest
```

## License

See LICENSE.
