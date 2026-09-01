from __future__ import annotations

import struct
from dataclasses import dataclass
from pathlib import Path

from pramaan.recovery.base import RecoveredSegment

DHAV_HEADER = b"DHAV"
DHAV_FOOTER = b"dhav"
MAX_FRAME_BYTES = 16 * 1024 * 1024
MIN_FRAME_BYTES = 32


@dataclass
class VendorHit:
    vendor: str
    adapter: str
    confidence: float
    markers: list[str]


def detect_vendors(image_path: Path, sample_bytes: int = 64 * 1024 * 1024) -> list[VendorHit]:
    data = _read_prefix(image_path, sample_bytes)
    hits: list[VendorHit] = []

    dhav_count = data.count(DHAV_HEADER)
    dhfs_markers = sum(1 for token in (b"DHFS", b"DHFS4", b"DHFS4.1") if token in data)
    hkvi_count = data.count(b"HKVI")
    hik_markers = sum(1 for token in (b"HIKVISION", b"HIKV", b"hkvs") if token in data)

    if dhav_count > 0 or dhfs_markers > 0:
        confidence = min(0.98, 0.55 + min(dhav_count, 50) * 0.008 + dhfs_markers * 0.05)
        markers = []
        if dhav_count:
            markers.append(f"DHAV×{dhav_count}")
        if dhfs_markers:
            markers.append("DHFS")
        hits.append(VendorHit("Dahua", "dahua_dhav", confidence, markers))

    if hkvi_count > 0 or hik_markers > 0:
        confidence = min(0.95, 0.5 + min(hkvi_count, 40) * 0.01 + hik_markers * 0.08)
        markers = []
        if hkvi_count:
            markers.append(f"HKVI×{hkvi_count}")
        if hik_markers:
            markers.append("HIKVISION")
        hits.append(VendorHit("Hikvision", "hikvision", confidence, markers))

    h264_hits = data.count(b"\x00\x00\x01") + data.count(b"\x00\x00\x00\x01")
    if h264_hits > 20 and not hits:
        hits.append(
            VendorHit(
                "Generic",
                "h264_carve",
                min(0.7, 0.35 + h264_hits * 0.002),
                [f"NAL×{h264_hits}"],
            )
        )

    hits.sort(key=lambda item: item.confidence, reverse=True)
    return hits


def _read_prefix(path: Path, nbytes: int) -> bytes:
    with path.open("rb") as handle:
        return handle.read(nbytes)


def _parse_dhav_frame(data: bytes, offset: int) -> tuple[int, int, str] | None:
    if offset + 16 > len(data):
        return None
    if data[offset : offset + 4] != DHAV_HEADER:
        return None

    # Dahua DHAV length field commonly at offset + 4 (little-endian uint32)
    frame_len = struct.unpack_from("<I", data, offset + 4)[0]
    if frame_len < MIN_FRAME_BYTES or frame_len > MAX_FRAME_BYTES:
        # Alternate layout: uint16 length at offset + 6
        frame_len = struct.unpack_from("<H", data, offset + 6)[0]
        if frame_len < MIN_FRAME_BYTES or frame_len > MAX_FRAME_BYTES:
            return None

    end = offset + frame_len
    if end > len(data):
        return None
    if data[end - 4 : end] != DHAV_FOOTER:
        return None

    channel = None
    if offset + 12 <= len(data):
        channel = int(data[offset + 11]) if data[offset + 11] < 64 else None

    return frame_len, channel or 0, "dual_signature"


class DahuaDhavAdapter:
    name = "dahua_dhav"
    vendor = "Dahua"

    def scan(self, image_path: Path, *, max_bytes: int | None = None) -> list[RecoveredSegment]:
        segments: list[RecoveredSegment] = []
        chunk_size = 8 * 1024 * 1024
        overlap = 64
        offset_base = 0
        total_read = 0
        carry = b""

        with image_path.open("rb") as handle:
            while True:
                if max_bytes is not None and total_read >= max_bytes:
                    break
                chunk = handle.read(chunk_size)
                if not chunk:
                    break
                total_read += len(chunk)
                window = carry + chunk
                local_offset = 0
                while True:
                    hit = window.find(DHAV_HEADER, local_offset)
                    if hit < 0:
                        break
                    parsed = _parse_dhav_frame(window, hit)
                    if parsed:
                        frame_len, channel, validation = parsed
                        abs_start = offset_base - len(carry) + hit
                        abs_end = abs_start + frame_len
                        segments.append(
                            RecoveredSegment(
                                channel=channel,
                                vendor=self.vendor,
                                offset_start=abs_start,
                                offset_end=abs_end,
                                frame_count=1,
                                confidence=0.92,
                                validation=validation,
                                raw_bytes=window[hit : hit + frame_len],
                            )
                        )
                        local_offset = hit + frame_len
                    else:
                        local_offset = hit + 4

                carry = window[-overlap:] if len(window) > overlap else window
                offset_base += len(chunk)

        return _merge_adjacent(segments)


def _merge_adjacent(segments: list[RecoveredSegment]) -> list[RecoveredSegment]:
    if not segments:
        return []
    segments.sort(key=lambda s: s.offset_start)
    merged: list[RecoveredSegment] = [segments[0]]
    for seg in segments[1:]:
        last = merged[-1]
        if (
            seg.channel == last.channel
            and seg.vendor == last.vendor
            and seg.offset_start <= last.offset_end + 4096
        ):
            merged[-1] = RecoveredSegment(
                channel=last.channel,
                vendor=last.vendor,
                offset_start=last.offset_start,
                offset_end=max(last.offset_end, seg.offset_end),
                frame_count=last.frame_count + seg.frame_count,
                confidence=min(last.confidence, seg.confidence),
                validation=last.validation,
                raw_bytes=b"",
            )
        else:
            merged.append(seg)
    return merged
