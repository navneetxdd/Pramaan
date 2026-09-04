#!/usr/bin/env python3
"""Print the Hikvision engine's recording output so downstream work can build against it.

Handoff artifact for the Recovery page / playback pipeline: it dumps the exact dict shape
``HikvisionAdapter.list_recordings()`` returns, plus the allocation-state counts the Recovery
header and the deleted-only filter are driven from.

The field set is contractual and documented in ``docs/reference/hikvision_fs.md`` §9::

    channel, start_ts, end_ts, byte_offset, byte_length,
    event_type, resolution, fps, allocation_state

Usage::

    python scripts/validation/verify_engine_output.py                # emulated image
    python scripts/validation/verify_engine_output.py <image.img>    # a real acquisition
    python scripts/validation/verify_engine_output.py --json         # machine-readable

Exit status is 0 when every contract check passes, 1 otherwise, so this is usable as a CI
gate. Against a real image the ground-truth counts are unknown, so the count assertions are
reported as INFO rather than PASS/FAIL — only the schema and internal-consistency checks are
enforced.

NOTE ON PROVENANCE: with no image argument this runs against the EMULATED image built by
``engine/tests/support/hikvision_builder.py`` — a faithful reconstruction of the published
filesystem layout, not a field acquisition. The banner says so on every run. Do not present
its output as evidence from a real recorder.
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

RULE = "=" * 78
THIN = "-" * 78

# docs/reference/hikvision_fs.md §9 — order is contractual, not incidental.
OUTPUT_CONTRACT = [
    "channel",
    "start_ts",
    "end_ts",
    "byte_offset",
    "byte_length",
    "event_type",
    "resolution",
    "fps",
    "allocation_state",
]


def _check(label: str, ok: bool, detail: str = "") -> bool:
    print(f"{label:<42}: {'PASS' if ok else 'FAIL'}{('  ' + detail) if detail else ''}")
    return ok


def _info(label: str, value: object) -> None:
    print(f"{label:<42}: {value}")


def _provenance_of(image: Path) -> str:
    """Describe where a supplied image came from.

    This script must never label a fabricated image as a real acquisition. Generated images
    carry a stamp in their first sector; anything without one is reported as UNVERIFIED,
    because a file path alone is not evidence of provenance.
    """
    with image.open("rb") as handle:
        head = handle.read(64)
    if b"PRAMAAN-EMULATED-HIKVISION-FS" in head:
        return "EMULATED - NOT a real acquisition"
    if b"PRAMAAN-LAB-SPECIMEN-HIKVISION" in head:
        return "LAB SPECIMEN - fabricated, NOT a real acquisition"
    return "UNVERIFIED - operator-supplied; confirm provenance from the custody record"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("image", nargs="?", help="Hikvision disk image; omit to use the emulated image")
    parser.add_argument("--json", action="store_true", help="emit the recording list as JSON and nothing else")
    args = parser.parse_args()

    sys.path.insert(0, str(ROOT))
    from engine.app.parsers.hikvision import HikvisionAdapter
    from engine.app.parsers.schemas import hikvision_fs as fs

    tmpdir: tempfile.TemporaryDirectory | None = None
    expected_count: int | None = None
    expected_deleted: int | None = None
    sources: tuple[str, ...] = ()

    if args.image:
        image = Path(args.image)
        if not image.is_file():
            print(f"error: no such image: {image}", file=sys.stderr)
            return 1
        provenance = _provenance_of(image)
    else:
        from engine.tests.support import hikvision_builder as builder

        tmpdir = tempfile.TemporaryDirectory(prefix="pramaan-verify-")
        built = builder.build_emulated_image(Path(tmpdir.name) / "hikvision_emulated.img")
        image = built.path
        provenance = "EMULATED - NOT a real acquisition"
        expected_count = built.expected_count
        expected_deleted = built.expected_deleted
        sources = built.sources

    try:
        adapter = HikvisionAdapter()
        records = adapter.list_recordings(image)

        if args.json:
            print(json.dumps(records, indent=2))
            return 0

        print(RULE)
        print("PRAMAAN / SIH26150 - Hikvision proprietary filesystem engine")
        print("Reference: docs/reference/hikvision_fs.md")
        print(RULE)
        _info("image", image)
        _info("image bytes", f"{image.stat().st_size:,}")
        _info("provenance", provenance)
        for source in sources:
            _info("  source", source)

        print()
        print(THIN)
        print("ENGINE OUTPUT CONTRACT  (reference doc section 9)")
        print(THIN)
        if not records:
            print("no recordings recovered from this image")
        for index, record in enumerate(records, 1):
            print(f"[{index}] {json.dumps(record, indent=6)}")

        print()
        print(THIN)
        print("CONTRACT CHECKS")
        print(THIN)
        ok = True
        ok &= _check("recordings recovered", bool(records), f"{len(records)} found")
        ok &= _check(
            "field set and order identical everywhere",
            all(list(record) == OUTPUT_CONTRACT for record in records),
            str(OUTPUT_CONTRACT),
        )
        ok &= _check(
            "byte ranges non-empty and inside image",
            all(0 < record["byte_length"] and record["byte_offset"] + record["byte_length"] <= image.stat().st_size
                for record in records),
        )
        ok &= _check(
            "allocation_state from the documented set",
            all(record["allocation_state"] in {fs.STATE_ALLOCATED, fs.STATE_RECORDING, fs.STATE_DELETED}
                for record in records),
        )
        ok &= _check(
            "event_type from the documented set",
            all(record["event_type"] in {fs.EVENT_CONTINUOUS, fs.EVENT_EVENT, fs.EVENT_UNKNOWN}
                for record in records),
        )

        counts = fs.summarize(fs.list_recordings(image.read_bytes())) if records else {}
        deleted = [record for record in records if record["allocation_state"] == fs.STATE_DELETED]

        if expected_count is not None:
            ok &= _check("recording count matches ground truth", len(records) == expected_count,
                         f"{len(records)} of {expected_count}")
            ok &= _check("deleted count matches ground truth", len(deleted) == expected_deleted,
                         f"{len(deleted)} of {expected_deleted}")
        else:
            _info("recordings recovered (no ground truth)", len(records))
            _info("deleted recovered (no ground truth)", len(deleted))

        print()
        print(THIN)
        print("RECOVERY PAGE SUMMARY  (feeds the header count and the deleted-only filter)")
        print(THIN)
        _info("allocation states", json.dumps(counts))
        _info("channels", sorted({record["channel"] for record in records}))
        _info("event types", sorted({record["event_type"] for record in records}))
        _info("resolutions", sorted({str(record["resolution"]) for record in records}))
        _info("frame rates", sorted({str(record["fps"]) for record in records}))

        segments = adapter.scan(image)
        if deleted:
            print()
            print(THIN)
            print("DELETED ENTRY DETAIL  (reference doc section 7)")
            print(THIN)
            for segment in (s for s in segments if s.validation == "hikbtree_deleted_entry"):
                evidence = segment.validation_evidence
                _info("validation", segment.validation)
                _info("allocation_state", evidence["allocation_state"])
                _info("channel / byte range",
                      f"ch{segment.channel}  {segment.offset_start:#x} .. {segment.offset_end:#x} "
                      f"({segment.offset_end - segment.offset_start:,} bytes)")
                _info("timestamp_source", segment.timestamp_source)
                _info("timestamp_confidence", segment.timestamp_confidence)
                _info("basis", evidence["timestamp_confidence_basis"])
                print()
            allocated = [s for s in segments if s.validation == "hikbtree_indexed"]
            if allocated:
                worst_deleted = min(
                    (s.timestamp_confidence or 0) for s in segments if s.validation == "hikbtree_deleted_entry"
                )
                ok &= _check(
                    "deleted confidence below allocated",
                    worst_deleted < (allocated[0].timestamp_confidence or 0),
                    f"{worst_deleted} < {allocated[0].timestamp_confidence}",
                )

        print()
        print(THIN)
        print("MEMORY CONTRACT  (reference doc section 10)")
        print(THIN)
        retained = sum(len(segment.raw_bytes) for segment in segments)
        ok &= _check("no payload retained per segment", retained == 0, f"{retained} bytes")

        print(RULE)
        print("RESULT: " + ("ALL CHECKS PASSED" if ok else "CHECKS FAILED"))
        print(RULE)
        return 0 if ok else 1
    finally:
        if tmpdir is not None:
            tmpdir.cleanup()


if __name__ == "__main__":
    raise SystemExit(main())
