# DEVIATIONS.md

Log of corrections and gaps between the SIH26150 Master Build Prompt v1.0 and this repository.

## 2026-09-01 — M5 Case export/import + AI analytics

- Signed `.pramaan.zip` bundles with RSA-PSS manifest signatures and per-file SHA-256 verification on import.
- AI analytics uses ffmpeg scene detection at 1 fps; OpenCV Haar face candidates when a full `opencv-python` install is present (YuNet ONNX not bundled — see limitations).
- Face/motion findings stored in `ai_findings` and surfaced on timeline + AI Analytics screen with mandatory disclaimer banner.

## 2026-09-01 — M4 Physical acquisition

- Block imaging implemented: chunked read, checkpoints, resume, bad-sector map, read-only source policy.
- Windows `\\.\PhysicalDriveN` enumeration requires admin; lab/dev uses file-as-source imaging (same code path).
- E01 **input** optional via `pyewf`; E01 **output** not implemented — writes raw DD + sidecar SHA-256.
- Physical USB write-blocker integration is operator-side; engine enforces read-only file opens only.

## 2026-09-01 — M3 Honeywell + Tier 2 filesystem

- Honeywell G.3.3 parser implemented: GPT/sector-34 detection, partition header, channel index (expiration deletion), raw video-region scan (format deletion).
- Generic Tier 2 adapter: `pytsk3` filesystem undelete when mount succeeds; manual FAT deleted-entry walk + H.264 carve degradation path when not.
- `pytsk3` added to `engine/requirements.txt` (verified on Windows/Python 3.13).

## 2026-09-01 — CFReDS / Digital Corpora (M3 check)

Checked **2026-09-01** (unchanged from M0):

| Source | Result |
|--------|--------|
| [CFReDS](https://cfreds.nist.gov/) | General forensic training sets (Hacking Case, Data Leakage, Drone Images, Registry Forensics). **No multi-vendor DVR/NVR raw disk images.** |
| [Digital Corpora](https://digitalcorpora.org/) | NPS NTFS/FAT test images, CTF corpora — useful for Tier 2 filesystem/carve testing. **No vendor DHFS/Hikvision store specimens.** |

Pramaan uses in-repo synthetic Dahua + Honeywell + Hikvision lab specimens until operator-supplied images are available.

## 2026-09-01 — Validation asset pipeline

| Asset | Source | Purpose |
|-------|--------|---------|
| `validation_data/fixtures/tier1/*.bin` | Generated (`scripts/fetch_validation_assets.py`) | Known-answer Dahua/Honeywell/Hikvision recovery |
| `validation_data/fixtures/tier2/fat16_deleted_entry.img` | Generated | Tier-2 filesystem undelete regression |
| `validation_data/models/face_detection_yunet_2023mar.onnx` | [OpenCV HuggingFace](https://huggingface.co/opencv/face_detection_yunet) | YuNet face detection when OpenCV DNN supports it |
| `validation_data/external/digitalcorpora/*/narrative.txt` | Digital Corpora (NIST-affiliated) | Tier-2 corpus metadata; full `.raw` images optional (`--large`) |
| `validation_data/oem/` | **Operator / NTRO only** | Drop real DVR `.bin`/`.dd`/`.raw` — set `PRAMAAN_OEM_IMAGE_DIR` |

**Not available publicly:** multi-vendor DVR/NVR disk images (Dahua DHFS, Hikvision HIKBTREE, Honeywell GPT). CFReDS and Digital Corpora confirmed 2026-09-01 — no OEM store specimens.

## 2026-09-01 — M2 parser depth

- Dahua DHAV and Hikvision HKVI `construct` schemas with 4-check validation.
- PAdES signing certificate persists under `{FORENSIC_WORKSTATION_DATA}/signing/`.
- Jobs left `running`/`pending` at engine restart reconcile to `interrupted`.

## 2026-09-01 — M0 restructure

- Repo layout moved from `frontend/src` + `frontend/src-tauri` to root `/src`, `/src-tauri` per Part D.
- `backend/pramaan/` deleted; all forensic logic lives in `engine/app/`.
- `/api/*` legacy compat layer removed; frontend fully migrated to `/api/v1/*`.
- FastAPI no longer serves the built SPA; `python run.py` is backend-only dev mode.

## Known deviations (remaining)

- YuNet/YOLOX ONNX models not bundled — motion via ffmpeg; face via OpenCV Haar when available.
- E01 output imaging not implemented — DD + SHA-256 sidecar only.
- PyInstaller freeze, code signing, Part I.4 release checklist scheduled M6.

## Correction log

| Date | Item | Reason |
|------|------|--------|
| 2026-09-01 | M3 Honeywell + Tier 2 filesystem | Architecture plan M3 exit criteria |
| 2026-09-01 | M2 construct parsers + PAdES persistence | Tier-1 hardening |
| 2026-09-01 | M0 repo + API consolidation | Eliminate dual backend |
