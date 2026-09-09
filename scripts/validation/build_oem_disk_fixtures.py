#!/usr/bin/env python3
"""Wrap tier-1 lab specimens in disk-shaped images for OEM acquire / import testing.

These are NOT field DVR captures. Public Hikvision/Dahua disk images do not exist on
Digital Corpora or CFReDS. This script produces minimum-size .img files with OEM
signatures at realistic offsets plus embedded known-answer parser bytes.
"""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OEM_DIR = ROOT / "validation_data" / "oem"
DISK_SIZE = 4 * 1024 * 1024


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


import struct

def build_dahua_disk(specimen: bytes) -> bytes:
    disk = bytearray(DISK_SIZE)
    # Master header with DHFS4.1 signature
    header = b"DHFS4.1" + b"\x00" * (1024 - len("DHFS4.1"))
    disk[0:len(header)] = header
    
    embed_at = 512 * 1024
    disk[embed_at:embed_at + len(specimen)] = specimen
    
    # Build a mock DHFS index at offset 1024
    # Format: Magic "DHID", uint32 count, then entries.
    # We will mark the first half of the specimen as allocated, and the second half as deleted.
    index_offset = 1024
    disk[index_offset:index_offset+4] = b"DHID"
    
    entries = []
    # Recording 1: Allocated (Start to roughly half)
    entries.append(struct.pack("<BBHIIQQI", 1, 1, 0, 0, 0, embed_at, embed_at + 8192, 0))
    # Recording 2: Deleted (The rest)
    entries.append(struct.pack("<BBHIIQQI", 2, 0, 0, 0, 0, embed_at + 8192, embed_at + len(specimen), 0))
    
    struct.pack_into("<I", disk, index_offset+4, len(entries))
    offset = index_offset + 8
    for entry in entries:
        disk[offset:offset+32] = entry
        offset += 32
        
    return bytes(disk)


def build_hikvision_disk(specimen: bytes) -> bytes:
    # Hikvision specimen already includes markers at 512/1024 offsets. Never truncate —
    # the HIKBTREE entries the specimen builder writes live near the end of the buffer,
    # and cutting it down to DISK_SIZE silently drops every recording (confirmed: this
    # exact truncation is why list_recordings() returned 0 on the previously-committed
    # lab_hikvision_fs.img after build_hikvision_lab_specimen() grew past 4 MiB).
    if len(specimen) >= DISK_SIZE:
        return specimen
    disk = bytearray(DISK_SIZE)
    disk[:len(specimen)] = specimen
    return bytes(disk)


def build_honeywell_disk(specimen: bytes) -> bytes:
    disk = bytearray(DISK_SIZE)
    disk[0:len(specimen)] = specimen
    return bytes(disk)


def main() -> int:
    sys.path.insert(0, str(ROOT))
    from engine.app.verification.builder_specimen import build_dahua_builder_specimen
    from engine.app.verification.hikvision_specimen import build_hikvision_builder_specimen
    from engine.app.verification.honeywell_specimen import build_honeywell_builder_specimen

    OEM_DIR.mkdir(parents=True, exist_ok=True)
    builds = [
        ("lab_dahua_dhfs.img", build_dahua_disk(build_dahua_builder_specimen())),
        ("lab_hikvision_fs.img", build_hikvision_disk(build_hikvision_builder_specimen())),
        ("lab_honeywell_fs.img", build_honeywell_disk(build_honeywell_builder_specimen())),
    ]

    for name, blob in builds:
        dest = OEM_DIR / name
        dest.write_bytes(blob)
        print(f"  wrote {dest.name} ({len(blob)} bytes) sha256={_sha256(blob)[:16]}…")

    print(f"\nOEM drop zone: {OEM_DIR}")
    print("Use Acquisition OEM drop folder, or Import with handler + case title.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
