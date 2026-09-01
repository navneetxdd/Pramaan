from __future__ import annotations

from pathlib import Path

from pramaan.recovery.base import RecoveredSegment

NAL_START_3 = b"\x00\x00\x01"
NAL_START_4 = b"\x00\x00\x00\x01"
MAX_GOP_BYTES = 4 * 1024 * 1024


class H264CarveAdapter:
    name = "h264_carve"
    vendor = "Generic"

    def scan(self, image_path: Path, *, max_bytes: int | None = None) -> list[RecoveredSegment]:
        segments: list[RecoveredSegment] = []
        chunk_size = 4 * 1024 * 1024
        carry = b""
        offset_base = 0
        total_read = 0
        active_start: int | None = None
        active_abs_start: int | None = None
        bytes_in_gop = 0

        with image_path.open("rb") as handle:
            while True:
                if max_bytes is not None and total_read >= max_bytes:
                    break
                chunk = handle.read(chunk_size)
                if not chunk:
                    break
                total_read += len(chunk)
                window = carry + chunk
                i = 0
                while i < len(window) - 4:
                    if window.startswith(NAL_START_4, i) or window.startswith(NAL_START_3, i):
                        abs_pos = offset_base - len(carry) + i
                        if active_start is None:
                            active_start = i
                            active_abs_start = abs_pos
                            bytes_in_gop = 0
                        bytes_in_gop = abs_pos - (active_abs_start or abs_pos)
                        if bytes_in_gop >= MAX_GOP_BYTES:
                            segments.append(
                                RecoveredSegment(
                                    channel=None,
                                    vendor=self.vendor,
                                    offset_start=active_abs_start or abs_pos,
                                    offset_end=abs_pos,
                                    frame_count=1,
                                    confidence=0.62,
                                    validation="h264_nal",
                                    raw_bytes=b"",
                                )
                            )
                            active_start = i
                            active_abs_start = abs_pos
                            bytes_in_gop = 0
                        i += 3
                    else:
                        i += 1
                carry = window[-16:]
                offset_base += len(chunk)

        if active_abs_start is not None:
            segments.append(
                RecoveredSegment(
                    channel=None,
                    vendor=self.vendor,
                    offset_start=active_abs_start,
                    offset_end=offset_base,
                    frame_count=1,
                    confidence=0.55,
                    validation="h264_nal_tail",
                    raw_bytes=b"",
                )
            )

        return segments
