"""Container -> elementary-stream demuxers used at recovery-write time.

The recovery adapters locate and validate frame boundaries inside a vendor
container (DHAV frames, Hikvision picture-index blocks, Honeywell NAL headers).
Until now the write step copied the *container* byte range verbatim and named it
``.h264`` — so the artifact was a renamed copy of the input, never a real
elementary stream. These functions do the repackage the adapters stopped short
of: strip the vendor wrapper frame by frame and concatenate the underlying
Annex-B payloads, losslessly (no decode, no re-encode).

Design rules:
  * Never inject parameter sets that were not in the source. A recorder stream
    carries its own SPS/PPS/VPS in the I-frames; adding fixture parameter sets to
    real evidence is forensically wrong. ``ensure_playable_h264`` is only applied
    downstream to *carves*, never here.
  * Preserve file order. FFmpeg's DHAV demuxer emits packets in file order; a
    frame-number sort can reorder a stream whose counter wrapped or reset.
  * Count honestly. ``frames_detected`` is what the wrapper claimed; a
    ``frames_extracted`` that is lower is surfaced, never hidden.
"""

from __future__ import annotations

from dataclasses import dataclass, field

NAL_START_3 = b"\x00\x00\x01"
NAL_START_4 = b"\x00\x00\x00\x01"

# Container tags carried on RecoveredSegment.stream_container and understood by
# recovery._write_demuxed_artifact.
CONTAINER_DHAV = "dhav"
CONTAINER_HIKVISION_PICTURE_INDEX = "hikvision_picture_index"
CONTAINER_HONEYWELL_NAL = "honeywell_nal"
DEMUX_CONTAINERS = frozenset(
    {CONTAINER_DHAV, CONTAINER_HIKVISION_PICTURE_INDEX, CONTAINER_HONEYWELL_NAL}
)

# DHAV ext-TLV 0x81 video_codec byte -> codec name (libavformat/dhav.c).
_DHAV_VIDEO_CODEC = {
    0x1: "mpeg4",
    0x2: "h264",
    0x3: "mjpeg",
    0x4: "h264",
    0x8: "h264",
    0xC: "hevc",
}


@dataclass
class DemuxResult:
    stream: bytes
    codec: str  # "h264" | "hevc" | "mpeg4" | "mjpeg" | "unknown"
    frames_detected: int
    frames_extracted: int
    method: str
    notes: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return len(self.stream) > 0 and (NAL_START_3 in self.stream)

    @property
    def complete(self) -> bool:
        return (
            self.frames_extracted > 0
            and self.frames_extracted == self.frames_detected
        )

    @property
    def file_suffix(self) -> str:
        return {
            "h264": ".h264",
            "hevc": ".h265",
            "mpeg4": ".m4v",
            "mjpeg": ".mjpeg",
        }.get(self.codec, ".bin")


def demux_container(data: bytes, container: str) -> DemuxResult:
    if container == CONTAINER_DHAV:
        return demux_dhav(data)
    if container == CONTAINER_HIKVISION_PICTURE_INDEX:
        return demux_hikvision_picture_index(data)
    if container == CONTAINER_HONEYWELL_NAL:
        return demux_honeywell_nal(data)
    raise ValueError(f"unknown demux container {container!r}")


# -- shared helpers -----------------------------------------------------------------


def _with_start_code(payload: bytes) -> bytes:
    """Prepend a 4-byte Annex-B start code only when the payload lacks one.

    DHAV / Hikvision / Honeywell payloads on real hardware already begin
    ``00 00 00 01``; this is a guard for a truncated first frame, not a rewrite.
    """
    if payload.startswith(NAL_START_4) or payload.startswith(NAL_START_3):
        return payload
    return NAL_START_4 + payload


def _first_nal_after_start(stream: bytes) -> bytes | None:
    """Bytes of the first NAL unit (header byte first), start code stripped."""
    i = stream.find(NAL_START_3)
    if i < 0:
        return None
    i += 3
    if i < len(stream) and stream[i] == 0x00:  # was a 4-byte start code
        i += 1
    j = stream.find(NAL_START_3, i)
    return stream[i:j] if j >= 0 else stream[i:]


def sniff_codec(stream: bytes) -> str | None:
    """h264 vs hevc from the first parameter-set NAL. Returns None if unclear."""
    nal = _first_nal_after_start(stream)
    if not nal:
        return None
    b0 = nal[0]
    h264_type = b0 & 0x1F
    if h264_type == 7:  # SPS
        return "h264"
    hevc_type = (b0 >> 1) & 0x3F
    if b0 & 0x80 == 0 and hevc_type in (32, 33, 34):  # VPS / SPS / PPS
        return "hevc"
    if h264_type in (1, 5) and (b0 & 0x80) == 0:
        return "h264"
    return None


# -- DHAV --------------------------------------------------------------------------


def _dhav_ext_codec(ext: bytes) -> str | None:
    """video_codec name from the 0x81 TLV in one DHAV frame's extension block."""
    from engine.app.parsers.schemas.dhav import _EXT_CONSUME

    i = 0
    n = len(ext)
    while i < n:
        t = ext[i]
        if t == 0x81 and i + 3 < n:
            return _DHAV_VIDEO_CODEC.get(ext[i + 2])
        step = _EXT_CONSUME.get(t)
        if not step:
            break
        i += step
    return None


def demux_dhav(data: bytes) -> DemuxResult:
    from engine.app.parsers.schemas.dhav import (
        DHAV_FOOTER_SIZE,
        DHAV_HEADER,
        DHAV_HEADER_SIZE,
        DHAV_TYPE_I,
        DHAV_TYPE_P,
        validate_dhav_frame,
    )

    out = bytearray()
    detected = 0
    extracted = 0
    codec: str | None = None
    notes: list[str] = []
    off = 0
    n = len(data)

    while off + DHAV_HEADER_SIZE <= n:
        if data[off : off + 4] != DHAV_HEADER:
            nxt = data.find(DHAV_HEADER, off + 1)
            if nxt < 0:
                break
            off = nxt
            continue
        parsed = validate_dhav_frame(data, off)
        if parsed is None or not parsed.checks["size_consistency"]:
            off += 4
            continue
        frame_len = parsed.frame_len
        ext_len = data[off + 22]
        if parsed.frame_type in (DHAV_TYPE_I, DHAV_TYPE_P):
            detected += 1
            if codec is None:
                codec = _dhav_ext_codec(
                    data[off + DHAV_HEADER_SIZE : off + DHAV_HEADER_SIZE + ext_len]
                )
            payload_start = off + DHAV_HEADER_SIZE + ext_len
            payload_end = off + frame_len - DHAV_FOOTER_SIZE
            if 0 <= payload_start < payload_end <= n:
                out += _with_start_code(bytes(data[payload_start:payload_end]))
                extracted += 1
            else:
                notes.append(f"frame @{off:#x}: payload bounds invalid, omitted")
        off += frame_len

    if codec is None:
        codec = sniff_codec(bytes(out)) or "h264"
        notes.append("codec inferred from stream (no 0x81 codec TLV in range)")
    if detected and extracted < detected:
        notes.append(
            f"{detected - extracted} of {detected} video frame(s) had unreadable "
            "payloads and were omitted"
        )
    return DemuxResult(
        bytes(out), codec, detected, extracted, "dhav_frame_strip", notes
    )


# -- Hikvision picture-index -----------------------------------------------------------

_PIC_BA = b"\x00\x00\x01\xba"
_PIC_BC = b"\x00\x00\x01\xbc"
# magic(4) + struct.pack("<I", 0x10000000 | index)(4). See
# engine/app/verification/hikvision_specimen.py and hikvision_fs.md section 5.1.
_PIC_HEADER_LEN = 8


def _first_pic(data: bytes, start: int, end: int) -> int:
    a = data.find(_PIC_BA, start, end)
    b = data.find(_PIC_BC, start, end)
    hits = [p for p in (a, b) if p >= 0]
    return min(hits) if hits else -1


def demux_hikvision_picture_index(data: bytes) -> DemuxResult:
    n = len(data)
    notes: list[str] = []
    first = _first_pic(data, 0, n)

    if first < 0:
        # No proprietary headers in this range. If it already looks like an
        # elementary stream, pass it through untouched; otherwise report nothing.
        if NAL_START_3 in data:
            return DemuxResult(
                bytes(data),
                sniff_codec(data) or "h264",
                0,
                0,
                "passthrough",
                ["no picture-index headers; byte range already Annex-B"],
            )
        return DemuxResult(
            b"", "h264", 0, 0, "hikvision_picture_index_strip",
            ["no picture-index headers and no NAL start codes in range"],
        )

    if first > 0:
        notes.append(f"{first} byte(s) before the first picture-index header dropped")

    out = bytearray()
    detected = 0
    extracted = 0
    cursor = first
    while cursor >= 0 and cursor < n:
        if data[cursor : cursor + 4] not in (_PIC_BA, _PIC_BC):
            nxt = _first_pic(data, cursor + 1, n)
            cursor = nxt
            continue
        detected += 1
        nal_start = cursor + _PIC_HEADER_LEN
        nxt = _first_pic(data, nal_start, n)
        nal_end = nxt if nxt >= 0 else n
        chunk = bytes(data[nal_start:nal_end]).rstrip(b"\x00")
        if chunk:
            out += _with_start_code(chunk)
            extracted += 1
        cursor = nxt

    if detected and extracted < detected:
        notes.append(
            f"{detected - extracted} of {detected} picture-index block(s) held no "
            "NAL payload and were omitted"
        )
    codec = sniff_codec(bytes(out)) or "h264"
    return DemuxResult(
        bytes(out), codec, detected, extracted,
        "hikvision_picture_index_strip", notes,
    )


# -- Honeywell per-frame NAL header --------------------------------------------------


def demux_honeywell_nal(data: bytes) -> DemuxResult:
    from engine.app.parsers.schemas.honeywell import HoneywellNalHeader

    HEADER_LEN = 20
    MARKER = b"\x80\x01\x00"
    out = bytearray()
    detected = 0
    extracted = 0
    notes: list[str] = []
    off = 0
    n = len(data)

    while off + HEADER_LEN <= n:
        if data[off] in (0x82, 0x02) and data[off + 1 : off + 4] == MARKER:
            try:
                parsed = HoneywellNalHeader.parse(bytes(data[off : off + HEADER_LEN]))
                nal_length = int(parsed.nal_length)
            except Exception:
                off += 1
                continue
            detected += 1
            payload_start = off + HEADER_LEN
            payload_end = payload_start + nal_length
            if nal_length > 0 and payload_end <= n:
                out += _with_start_code(bytes(data[payload_start:payload_end]))
                extracted += 1
                off = payload_end
                continue
            notes.append(f"frame @{off:#x}: declared NAL length runs past the range")
            off += HEADER_LEN
            continue
        nxt = data.find(MARKER, off + 1)
        if nxt < 1:
            break
        off = nxt - 1

    if detected == 0 and NAL_START_3 in data:
        return DemuxResult(
            bytes(data), "h264", 0, 0, "passthrough",
            ["no Honeywell NAL headers; byte range already Annex-B"],
        )
    if detected and extracted < detected:
        notes.append(
            f"{detected - extracted} of {detected} Honeywell frame header(s) had "
            "unreadable payloads and were omitted"
        )
    return DemuxResult(
        bytes(out), "h264", detected, extracted, "honeywell_nal_header_strip", notes
    )
