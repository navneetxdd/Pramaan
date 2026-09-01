# Pramaan

Multi-vendor DVR/NVR forensic workstation for standardized acquisition, recovery, and analysis of surveillance evidence (SIH26150 / NTRO).

## Modular architecture (team integration)

Each forensic capability is a **lego brick** under `backend/pramaan/modules/` with its own README, public Python API, and mountable FastAPI routes. Shared contracts live in `backend/pramaan/schemas/`.

| Module | Directory | Responsibility |
|--------|-----------|----------------|
| Acquisition | `modules/acquisition/` | Disk image ingest, SHA-256 sidecar |
| Recovery | `modules/recovery/` | Vendor detector + pluggable adapters |
| Custody | `modules/custody/` | Hash-chained tamper-evident audit log |
| Analysis | `modules/analysis/` | Vendor-aware export (DHAV unwrap → MP4) |
| Reporting | `modules/reporting/` | JSON + HTML forensic reports |

**Env vars:** `PRAMAAN_*` (alias `CSHIELD_*` supported for team docs).  
**Data exchange:** JSON via REST; evidence files accompanied by `.sha256` sidecars.

```
backend/pramaan/
  schemas/       Pydantic contracts (import across modules)
  core/          SQLite WAL + case repository
  modules/       Self-contained forensic bricks
  recovery/      Adapter implementations (register via registry)
frontend/        Cipher Margin UI (Mirage-inspired)
```

## Research basis

Pramaan’s recovery methodology aligns with peer-reviewed forensic literature:

- **MDPI Information 2025** ([doi:10.3390/info16110983](https://doi.org/10.3390/info16110983)): dual-signature DHAV validation (header `DHAV` + footer `dhav`), adaptive temporal sequencing — reported 91.8% recovery, 2.4% false-positive rate vs header-only carving.
- **MDPI Information 2026** ([doi:10.3390/info17050493](https://doi.org/10.3390/info17050493)): multi-channel DHAV demultiplexing for analog Dahua DVR interleaved streams.
- **Hikvision FS analysis** (Han et al., ICDF2C 2015): HIKBTREE index structure — basis for HKVI adapter heuristics and future HIKBTREE parser (team slot).
- **Open-source references** (approaches, not copied): HIKVISION-DVR-Tool (E01 + timeline), dhfs_extractor, DVRExtractor (multi-FS: DHFS, WFS, HIKVISION).
- **Commercial gap:** Magnet WITNESS / Amped DVRConv are closed, siloed per-format; Pramaan targets **open, plugin-based** multi-vendor recovery with algorithmic transparency for court admissibility.

## Requirements

- Python 3.11+
- Node.js 20+
- FFmpeg on `PATH` (optional; MP4 export)

## Quick start

```bash
cd backend && pip install -r requirements.txt
cd .. && python run.py

cd frontend && npm install && npm run dev   # dev UI
cd frontend && npm run build && cd .. && python run.py   # prod UI
```

API: `http://127.0.0.1:8787`

## Forensic workflow

1. **Cases** — investigation registry with examiner metadata
2. **Acquire** — disk image + SHA-256 sidecar + vendor fingerprint hints
3. **Recover** — async job; Dahua DHAV / Hikvision HKVI / H.264 adapters
4. **Analyze** — offset timeline, vendor-aware segment export
5. **Custody** — hash-chained audit ledger with integrity verification
6. **Report** — JSON summary + printable HTML report

## Tests

```bash
cd backend && pytest
```

## License

See LICENSE.
