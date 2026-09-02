#!/usr/bin/env python3
"""Fetch licensed, reproducible validation assets and record unavailable sources."""

from __future__ import annotations

import hashlib
import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "validation_data"
MANIFEST_PATH = DATA_DIR / "manifest.json"

# Small, license-friendly downloads (Digital Corpora / OpenCV Zoo).
DOWNLOADS: list[dict] = [
    {
        "id": "digitalcorpora_ubnist1_narrative",
        "url": "https://downloads.digitalcorpora.org/corpora/drives/nps-2009-ubnist1/narrative.txt",
        "dest": "external/digitalcorpora/nps-2009-ubnist1/narrative.txt",
        "purpose": "Tier-2 FAT corpus reference (full ubnist1.gen3.raw is ~2.1 GB — fetch separately if needed)",
        "license": "NPS-created content is public domain; inspect embedded-file rights",
    },
    {
        "id": "digitalcorpora_xbox_narrative",
        "url": "https://downloads.digitalcorpora.org/corpora/drives/nps-2014-xbox1/narrative.txt",
        "dest": "external/digitalcorpora/nps-2014-xbox1/narrative.txt",
        "purpose": "Filesystem scenario metadata for extended tier-2 regression",
        "license": "NPS-created content is public domain; inspect embedded-file rights",
    },
    {
        "id": "yunet_face_detection",
        "url": "https://huggingface.co/opencv/face_detection_yunet/resolve/main/face_detection_yunet_2023mar.onnx",
        "dest": "models/face_detection_yunet_2023mar.onnx",
        "purpose": "Optional YuNet face detection for AI analytics (replaces Haar fallback when present)",
        "license": "Apache-2.0",
    },
    {
        "id": "yolox_nano_onnx",
        "url": "https://github.com/Megvii-BaseDetection/YOLOX/releases/download/0.1.1rc0/yolox_nano.onnx",
        "dest": "models/yolox_nano.onnx",
        "purpose": "YOLOX Nano COCO object-candidate detector for offline analytics",
        "license": "Apache-2.0",
    },
]

SURVEILLANCE_OPTIONAL = [
    {
        "id": "caviar_walk1_video",
        "url": "https://homepages.inf.ed.ac.uk/rbf/CAVIARDATA1/Walk1/Walk1.mpg",
        "dest": "external/caviar/Walk1.mpg",
        "purpose": "Real surveillance-style motion, face, and object candidate validation",
        "license": "CC BY-SA; acknowledge EC Funded CAVIAR project/IST 2001 37540",
    },
    {
        "id": "caviar_walk1_ground_truth",
        "url": "https://homepages.inf.ed.ac.uk/rbf/CAVIARDATA1/Walk1/wk1gt.xml",
        "dest": "external/caviar/wk1gt.xml",
        "purpose": "Hand-labelled CAVIAR person tracks for event-level validation",
        "license": "CC BY-SA; acknowledge EC Funded CAVIAR project/IST 2001 37540",
    },
]

LARGE_OPTIONAL = [
    {
        "id": "digitalcorpora_ubnist1_gen3",
        "url": "https://downloads.digitalcorpora.org/corpora/drives/nps-2009-ubnist1/ubnist1.gen3.raw",
        "dest": "external/digitalcorpora/nps-2009-ubnist1/ubnist1.gen3.raw",
        "bytes": 2_106_589_184,
        "purpose": "NPS FAT32 tier-2 filesystem regression (~2.1 GB)",
        "license": "NPS-created content is public domain; inspect embedded-file rights",
    },
]

REAL_FS_DOWNLOADS: list[dict] = [
    {
        "id": "digitalcorpora_nps_2009_canon2_gen6_e01",
        "url": "https://downloads.digitalcorpora.org/corpora/drives/nps-2009-canon2/nps-2009-canon2-gen6.E01",
        "dest": "external/digitalcorpora/nps-2009-canon2/nps-2009-canon2-gen6.E01",
        "sha256": "10483722d84e0cefcb693b11dea2d32dbd3ad2f06f8c9656688c8c730fe41579",
        "purpose": "NIST-affiliated public camera-card E01 for OEM/acquisition validation (~31 MB)",
        "license": "NPS-created content is public domain; inspect embedded-file rights",
    },
    {
        "id": "digitalcorpora_nps_2009_canon2_narrative",
        "url": "https://downloads.digitalcorpora.org/corpora/drives/nps-2009-canon2/narrative.txt",
        "dest": "external/digitalcorpora/nps-2009-canon2/narrative.txt",
        "sha256": "10613f6139d28f06d897fd9d19b2c3c679a1b28848c88f4877542f4c141fed84",
        "purpose": "Canon2 corpus narrative and scenario metadata",
        "license": "NPS-created content is public domain; inspect embedded-file rights",
    },
]

REAL_DVR_SAMPLES: list[dict] = [
    {
        "id": "dahua_dav_continuous",
        "url": "https://raw.githubusercontent.com/glepore70/pronom-research/master/sample_files/d/dav/19.25.00-19.25.50-R-.dav",
        "dest": "oem/dahua_19.25.00-19.25.50-R.dav",
        "purpose": "Real Dahua DHAV container for parser validation",
        "license": "PRONOM format sample — fetch-only",
    },
    {
        "id": "dahua_dav_motion",
        "url": "https://raw.githubusercontent.com/glepore70/pronom-research/master/sample_files/d/dav/20.49.55-20.50.21_M_0_0_0_.dav",
        "dest": "external/dvr/dahua/20.49.55-20.50.21_M_0_0_0_.dav",
        "purpose": "Real Dahua DHAV motion-event recording",
        "license": "PRONOM format sample — fetch-only",
    },
    {
        "id": "hikvision_nvr_export",
        "url": "https://samples.ffmpeg.org/camera-dvr/hikvision/DVR_NVR_IP%20Camera01_20130321162325_20130321162358_576877.mp4",
        "dest": "external/dvr/hikvision/DVR_NVR_IP_Camera01_20130321162325.mp4",
        "purpose": "Real Hikvision NVR export sample",
        "license": "FFmpeg sample archive — fetch-only",
    },
]

MEVA_SAMPLE = {
    "id": "meva_school_g474",
    "url": "https://mevadata-public-01.s3.amazonaws.com/drops-123-r13/2018-03-05/09/2018-03-05.09-49-37.09-50-00.school.G474.r13.avi",
    "dest": "external/meva/2018-03-05.09-49-37.school.G474.r13.avi",
    "purpose": "CC-BY real security-camera footage for analytics validation",
    "license": "CC-BY-4.0 MEVA",
}

CFREDS_DOWNLOADS: list[dict] = [
    {
        "id": "cfreds_dfr01_fat",
        "url": "https://cfreds-archive.nist.gov/dfr-images/dfr-01-fat.dd.bz2",
        "dest": "external/cfreds/dfr-01-fat.dd.bz2",
        "purpose": "NIST DFR-01 FAT deleted-file corpus",
        "license": "NIST public domain",
    },
]

REFERENCE_DOCS: list[dict] = [
    {
        "id": "ffmpeg_dhav_c",
        "url": "https://raw.githubusercontent.com/FFmpeg/FFmpeg/master/libavformat/dhav.c",
        "dest": "reference/dhav.c",
        "purpose": "Authoritative DHAV parser reference",
        "license": "LGPL — reference only",
    },
]

SOURCE_RECORDS = [
    {
        "id": "cdnet_2014_baseline",
        "source": "https://changedetection.net/",
        "status": "operator_fetch_required",
        "reason": "The benchmark site documents frame-level ground truth, but its dataset host was not resolvable during the 2026-09-01 release run.",
        "license": "Use requires benchmark acknowledgement and paper citation; redistribution is not asserted.",
    },
    {
        "id": "meva",
        "source": "https://mevadata.org/",
        "status": "operator_fetch_required",
        "reason": "Access terms and account requirements must be accepted by the operator; assets are not redistributed.",
    },
    {
        "id": "heimvision_dvr_evidence_image",
        "source": "https://digitalcorpora.org/corpora/disk-images/",
        "status": "unavailable",
        "reason": "No authoritative Heimvision DVR forensic disk image was located in Digital Corpora or CFReDS; unrelated media is not substituted.",
    },
]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _download(url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and dest.stat().st_size > 0:
        print(f"  skip (exists) {dest.name}")
        return
    print(f"  GET {url}")
    req = urllib.request.Request(url, headers={"User-Agent": "Pramaan-Validation-Fetch/1.0"})
    partial = dest.with_suffix(dest.suffix + ".part")
    partial.unlink(missing_ok=True)
    try:
        with urllib.request.urlopen(req, timeout=120) as resp, partial.open("wb") as out:
            while True:
                chunk = resp.read(1024 * 1024)
                if not chunk:
                    break
                out.write(chunk)
        partial.replace(dest)
    finally:
        partial.unlink(missing_ok=True)
    print(f"  saved {dest} ({dest.stat().st_size} bytes)")


def _sync_oem_drop_zone() -> list[str]:
    """Copy public corpora into validation_data/oem for OEM acquire UI testing."""
    oem_dir = DATA_DIR / "oem"
    oem_dir.mkdir(parents=True, exist_ok=True)
    synced: list[str] = []
    candidates = [
        DATA_DIR / "external" / "digitalcorpora" / "nps-2009-canon2" / "nps-2009-canon2-gen6.E01",
        DATA_DIR / "fixtures" / "tier2" / "fat16_deleted_entry.img",
        DATA_DIR / "oem" / "dahua_19.25.00-19.25.50-R.dav",
        DATA_DIR / "oem" / "lab_dahua_dhfs.img",
        DATA_DIR / "oem" / "lab_hikvision_fs.img",
        DATA_DIR / "oem" / "lab_honeywell_fs.img",
    ]
    for source in candidates:
        if not source.is_file():
            continue
        dest = oem_dir / source.name
        if dest.exists() and dest.stat().st_size == source.stat().st_size:
            synced.append(dest.name)
            continue
        dest.write_bytes(source.read_bytes())
        synced.append(dest.name)
        print(f"  synced OEM drop zone <- {source.name}")
    return synced


def _generate_fixtures() -> list[dict]:
    sys.path.insert(0, str(ROOT))
    from engine.app.parsers.filesystem_recovery import build_fat16_deleted_fixture
    from engine.app.verification.hikvision_specimen import build_hikvision_lab_specimen
    from engine.app.verification.honeywell_specimen import build_honeywell_lab_specimen
    from engine.app.verification.lab_specimen import build_dahua_lab_specimen

    fixtures: list[tuple[str, bytes]] = [
        ("fixtures/tier1/dahua_known_answer.bin", build_dahua_lab_specimen()),
        ("fixtures/tier1/honeywell_known_answer.bin", build_honeywell_lab_specimen()),
        ("fixtures/tier1/hikvision_known_answer.bin", build_hikvision_lab_specimen()),
        ("fixtures/tier2/fat16_deleted_entry.img", build_fat16_deleted_fixture()),
    ]
    out: list[dict] = []
    for rel, blob in fixtures:
        path = DATA_DIR / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(blob)
        out.append(
            {
                "id": rel.replace("/", "_").replace(".", "_"),
                "path": rel,
                "bytes": len(blob),
                "sha256": hashlib.sha256(blob).hexdigest(),
                "kind": "generated_known_answer",
            }
        )
        print(f"  wrote {rel} ({len(blob)} bytes)")
    return out


def main() -> int:
    include_large = "--large" in sys.argv
    include_surveillance = "--surveillance" in sys.argv
    include_real_fs = "--real-fs" in sys.argv
    include_real_dvr = "--real-dvr" in sys.argv
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    manifest: dict = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "note": (
            "Public DVR/NVR OEM disk images are NOT available from CFReDS or Digital Corpora. "
            "Place operator captures under validation_data/oem/ or set PRAMAAN_OEM_IMAGE_DIR."
        ),
        "assets": [],
        "large_optional": LARGE_OPTIONAL,
        "surveillance_optional": SURVEILLANCE_OPTIONAL,
        "source_records": SOURCE_RECORDS,
        "oem_env_var": "PRAMAAN_OEM_IMAGE_DIR",
    }

    print("Generating in-repo known-answer fixtures…")
    manifest["assets"].extend(_generate_fixtures())

    print("\nBuilding disk-shaped OEM lab images (vendor signatures at realistic offsets)…")
    try:
        import subprocess

        subprocess.run([sys.executable, str(ROOT / "scripts" / "validation" / "build_oem_disk_fixtures.py")], check=True)
    except (OSError, subprocess.CalledProcessError) as exc:
        print(f"  WARN: could not build OEM disk fixtures: {exc}")

    print("\nDownloading public assets…")
    for item in DOWNLOADS:
        dest = DATA_DIR / item["dest"]
        try:
            _download(item["url"], dest)
            manifest["assets"].append(
                {
                    "id": item["id"],
                    "path": item["dest"],
                    "bytes": dest.stat().st_size if dest.exists() else 0,
                    "sha256": _sha256(dest) if dest.exists() else None,
                    "url": item["url"],
                    "purpose": item["purpose"],
                    "license": item.get("license"),
                    "retrieved_at": datetime.now(timezone.utc).isoformat(),
                    "kind": "download",
                }
            )
        except (OSError, urllib.error.URLError) as exc:
            print(f"  FAILED {item['id']}: {exc}")
            manifest["assets"].append({"id": item["id"], "error": str(exc), "url": item["url"]})

    if include_surveillance:
        print("\nFetching licensed surveillance subset (--surveillance)…")
        for item in SURVEILLANCE_OPTIONAL + [MEVA_SAMPLE]:
            dest = DATA_DIR / item["dest"]
            try:
                _download(item["url"], dest)
                manifest["assets"].append(
                    {
                        "id": item["id"],
                        "path": item["dest"],
                        "bytes": dest.stat().st_size,
                        "sha256": _sha256(dest),
                        "url": item["url"],
                        "purpose": item["purpose"],
                        "license": item["license"],
                        "retrieved_at": datetime.now(timezone.utc).isoformat(),
                        "kind": "download_surveillance",
                    }
                )
            except (OSError, urllib.error.URLError) as exc:
                print(f"  FAILED {item['id']}: {exc}")
                manifest["assets"].append({"id": item["id"], "error": str(exc), "url": item["url"]})

    if include_real_dvr:
        print("\nFetching real DVR samples (--real-dvr)…")
        for item in REAL_DVR_SAMPLES:
            dest = DATA_DIR / item["dest"]
            try:
                _download(item["url"], dest)
                manifest["assets"].append(
                    {
                        "id": item["id"],
                        "path": item["dest"],
                        "bytes": dest.stat().st_size,
                        "sha256": _sha256(dest),
                        "url": item["url"],
                        "purpose": item["purpose"],
                        "license": item.get("license"),
                        "retrieved_at": datetime.now(timezone.utc).isoformat(),
                        "kind": "download_real_dvr",
                    }
                )
            except (OSError, urllib.error.URLError) as exc:
                print(f"  FAILED {item['id']}: {exc}")
                manifest["assets"].append({"id": item["id"], "error": str(exc), "url": item["url"]})

    for item in REFERENCE_DOCS:
        dest = ROOT / "docs" / "reference" / Path(item["dest"]).name
        try:
            _download(item["url"], dest)
        except (OSError, urllib.error.URLError) as exc:
            print(f"  WARN reference {item['id']}: {exc}")

    if include_real_fs:
        for item in CFREDS_DOWNLOADS:
            dest = DATA_DIR / item["dest"]
            try:
                _download(item["url"], dest)
                manifest["assets"].append(
                    {
                        "id": item["id"],
                        "path": item["dest"],
                        "bytes": dest.stat().st_size if dest.exists() else 0,
                        "sha256": _sha256(dest) if dest.exists() else None,
                        "url": item["url"],
                        "purpose": item["purpose"],
                        "license": item.get("license"),
                        "retrieved_at": datetime.now(timezone.utc).isoformat(),
                        "kind": "download_cfreds",
                    }
                )
            except (OSError, urllib.error.URLError) as exc:
                print(f"  FAILED {item['id']}: {exc}")

    if include_real_fs:
        print("\nFetching real filesystem corpora (--real-fs)…")
        for item in REAL_FS_DOWNLOADS:
            dest = DATA_DIR / item["dest"]
            try:
                _download(item["url"], dest)
                digest = _sha256(dest) if dest.exists() else None
                if item.get("sha256") and digest != item["sha256"]:
                    raise ValueError(f"SHA-256 mismatch for {item['id']}")
                manifest["assets"].append(
                    {
                        "id": item["id"],
                        "path": item["dest"],
                        "bytes": dest.stat().st_size if dest.exists() else 0,
                        "sha256": digest,
                        "url": item["url"],
                        "purpose": item["purpose"],
                        "license": item.get("license"),
                        "retrieved_at": datetime.now(timezone.utc).isoformat(),
                        "kind": "download_real_fs",
                    }
                )
            except (OSError, urllib.error.URLError, ValueError) as exc:
                print(f"  FAILED {item['id']}: {exc}")
                manifest["assets"].append({"id": item["id"], "error": str(exc), "url": item["url"]})

    if include_large:
        print("\nFetching large optional corpora (--large)…")
        for item in LARGE_OPTIONAL:
            dest = DATA_DIR / item["dest"]
            try:
                _download(item["url"], dest)
                manifest["assets"].append(
                    {
                        "id": item["id"],
                        "path": item["dest"],
                        "bytes": dest.stat().st_size,
                        "sha256": _sha256(dest),
                        "url": item["url"],
                        "purpose": item["purpose"],
                        "license": item.get("license"),
                        "retrieved_at": datetime.now(timezone.utc).isoformat(),
                        "kind": "download_large",
                    }
                )
            except (OSError, urllib.error.URLError) as exc:
                print(f"  FAILED {item['id']}: {exc}")

    oem_dir = DATA_DIR / "oem"
    oem_dir.mkdir(exist_ok=True)
    _sync_oem_drop_zone()
    manifest["oem_drop_zone"] = str(oem_dir.relative_to(ROOT))
    manifest["oem_files"] = sorted(p.name for p in oem_dir.iterdir() if p.is_file())

    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"\nManifest: {MANIFEST_PATH}")
    print(f"OEM images: drop real DVR dumps in {oem_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
