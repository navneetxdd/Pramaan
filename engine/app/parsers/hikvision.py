"""Hikvision recovery adapter.

Structure offsets and their sources: ``docs/reference/hikvision_fs.md``.

Memory contract (§10 of that document) — this adapter runs in a desktop shell against images
that can be multi-terabyte:

* Converting the whole mapping to a ``bytes`` object is forbidden; slice bounded windows only.
* No segment retains its payload. ``raw_bytes`` is always empty: ``recovery`` re-reads the byte
  range from the image when it writes the artifact.
* All byte scanning goes through ``find`` (C-level), never a Python ``range()`` loop.
"""

from __future__ import annotations

import mmap
from pathlib import Path

from engine.app.parsers.base import RecoveredSegment
from engine.app.parsers.schemas.hikvision_fs import (
    RECOVERY_PARTIAL,
    STATE_DELETED,
    STATE_RECORDING,
    TIMESTAMP_OK,
    TRAVERSAL_COMPLETE,
    RecordingEntry,
    RecoveryResult,
    find_master_block,
    parse_master_block,
    recover_recordings,
    summarize,
)

# Validation vocabulary surfaced to the Recovery menu and the report.
VALIDATION_BY_STATE = {
    "allocated": "hikbtree_indexed",
    STATE_RECORDING: "hikbtree_recording",
    STATE_DELETED: "hikbtree_deleted_entry",
}


class HikvisionAdapter:
    name = "hikvision"
    vendor = "Hikvision"
    version = "4"

    def scan(self, image_path: Path, *, max_bytes: int | None = None) -> list[RecoveredSegment]:
        return self._scan(image_path, max_bytes=max_bytes)

    def list_recordings(self, image_path: Path, *, max_bytes: int | None = None) -> list[dict]:
        """The engine output contract — docs/reference/hikvision_fs.md §9.

        Returns dicts with exactly: channel, start_ts, end_ts, byte_offset, byte_length,
        event_type, resolution, fps, allocation_state. This is what the playback pipeline
        consumes; ``scan()`` wraps the same data in the shared ``RecoveredSegment`` shape.
        """
        with self._mapped(image_path, max_bytes) as data:
            if data is None:
                return []
            return [item.as_dict() for item in recover_recordings(data).recordings]

    # -- internals ---------------------------------------------------------------------

    def _scan(self, image_path: Path, *, max_bytes: int | None) -> list[RecoveredSegment]:
        with self._mapped(image_path, max_bytes) as data:
            if data is None:
                return []
            master_offset = find_master_block(data)
            master = parse_master_block(data, master_offset) if master_offset is not None else None
            result = recover_recordings(data)
            counts = summarize(result.recordings)
            return [self._to_segment(item, master, counts, result) for item in result.recordings]

    class _Mapping:
        """Context manager yielding a read-only mmap, or None for an unusable image."""

        def __init__(self, path: Path, max_bytes: int | None) -> None:
            self._path = path
            self._max_bytes = max_bytes
            self._handle = None
            self._map = None

        def __enter__(self):
            self._handle = self._path.open("rb")
            file_size = self._handle.seek(0, 2)
            view_len = file_size if self._max_bytes is None else min(file_size, self._max_bytes)
            if view_len <= 0:
                self._handle.close()
                self._handle = None
                return None
            self._map = mmap.mmap(self._handle.fileno(), view_len, access=mmap.ACCESS_READ)
            return self._map

        def __exit__(self, *exc) -> None:
            if self._map is not None:
                self._map.close()
            if self._handle is not None:
                self._handle.close()
            return None

    def _mapped(self, image_path: Path, max_bytes: int | None) -> "HikvisionAdapter._Mapping":
        return self._Mapping(image_path, max_bytes)

    def _to_segment(
        self,
        item: RecordingEntry,
        master,
        counts: dict[str, int],
        result: RecoveryResult,
    ) -> RecoveredSegment:
        validation = VALIDATION_BY_STATE.get(item.allocation_state, "hikbtree_entry")
        return RecoveredSegment(
            channel=item.channel,
            vendor=self.vendor,
            offset_start=item.byte_offset,
            offset_end=item.byte_offset + item.byte_length,
            # The recorder writes one picture-index header per NAL unit, so this counts
            # container units, not decodable frames. The playback pipeline sets
            # playable_frame_count from ffprobe.
            frame_count=0,
            # docs/reference/hikvision_fs.md §7.1 — the documented three-rung ladder, not an
            # invented score. The checks that actually passed are in signature_evidence.
            confidence=item.timestamp_confidence if item.timestamp_confidence is not None else 0.3,
            validation=validation,
            raw_bytes=b"",
            codec="h264",
            recorder_start_ts=item.start_ts,
            recorder_end_ts=item.end_ts,
            timestamp_source=item.timestamp_source,
            timestamp_confidence=item.timestamp_confidence,
            parser_name=self.name,
            parser_version=self.version,
            signature_evidence={
                "master_block_signature": "HIKVISION@HANGZHOU",
                "master_block_offset": None if master is None else master.hikbtree_offset,
                "hikbtree_index": True,
                "firmware": None if master is None else master.version,
                "system_init_time": None if master is None else master.init_time_iso,
                "sps_decoded": item.resolution is not None,
                "idr_table_read": item.event_type != "unknown",
            },
            validation_evidence={
                # The §9 output contract, carried through to the Recovery page and report
                # without needing a change to the shared RecoveredSegment shape.
                "allocation_state": item.allocation_state,
                # Separate axis from allocation_state: what the *data* is, not what
                # the index says. Overwritten bytes are reported gone, never guessed.
                "recovery_status": item.recovery_status,
                "partial": item.recovery_status == RECOVERY_PARTIAL,
                "partial_reason": item.partial_reason,
                # Third axis, independent of the two above: whether the index entry's own
                # time fields are coherent. Raw timestamps are reported either way — an
                # inverted window is flagged, never silently reordered.
                "timestamp_status": item.timestamp_status,
                "timestamp_anomaly": item.timestamp_status != TIMESTAMP_OK,
                # The channel byte as read. `channel_valid` is False when that byte cannot
                # name a camera at all, so the UI never shows it as an ordinary source.
                "channel_valid": item.channel_valid,
                # Whether the recording inventory itself can be trusted to be whole:
                # "6 recordings" and "6 recordings before the index broke" differ.
                "index_traversal_status": result.traversal_status,
                "index_complete": result.traversal_status == TRAVERSAL_COMPLETE,
                "index_traversal_detail": result.traversal_detail,
                "index_pages_read": result.pages_visited,
                "event_type": item.event_type,
                "resolution": item.resolution,
                "fps": item.fps,
                "byte_offset": item.byte_offset,
                "byte_length": item.byte_length,
                "timestamp_confidence_basis": item.timestamp_confidence_basis,
                "deleted": item.allocation_state == STATE_DELETED,
                "recovery_context": validation,
                "image_allocation_counts": counts,
            },
        )
