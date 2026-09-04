"""Validation of the Hikvision filesystem engine.

Ground truth comes from ``engine/tests/support/hikvision_builder``, an EMULATED image built
from the published layout in ``docs/reference/hikvision_fs.md``. Nothing here round-trips
against structures the engine itself writes: the engine has no builders.

When a genuine acquired Hikvision drive becomes available, point ``_image()`` at it and the
expected counts at the hand-counted truth. Nothing else in this file needs to change.
"""

from __future__ import annotations

import struct
import tempfile
import unittest
from pathlib import Path

from engine.app.parsers.hikvision import HikvisionAdapter
from engine.app.parsers.schemas import hikvision_fs as fs
from engine.app.verification.media_fixture import caviar_nal_units
from engine.tests.support import hikvision_builder as builder

# The exact field set the playback pipeline consumes — reference doc §9.
OUTPUT_CONTRACT = {
    "channel",
    "start_ts",
    "end_ts",
    "byte_offset",
    "byte_length",
    "event_type",
    "resolution",
    "fps",
    "allocation_state",
    "recovery_status",
}


class HikvisionFsTestBase(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._tmp = tempfile.TemporaryDirectory(prefix="pramaan-hikfs-")
        cls.built = builder.build_emulated_image(Path(cls._tmp.name) / "hikvision_emulated.img")
        cls.blob = cls.built.path.read_bytes()

    @classmethod
    def tearDownClass(cls) -> None:
        cls._tmp.cleanup()


class MasterSectorTests(HikvisionFsTestBase):
    def test_master_block_parses_every_documented_field(self) -> None:
        master = fs.parse_master_block(self.blob, fs.MASTER_BLOCK_OFFSET)
        self.assertIsNotNone(master)
        assert master is not None
        self.assertEqual(master.signature, fs.HIKVISION_SIG)
        self.assertEqual(master.version, "V4.30.005")
        self.assertEqual(master.video_area_offset, builder.VIDEO_AREA_OFFSET)
        self.assertEqual(master.data_block_size, builder.DATA_BLOCK_SIZE)
        self.assertEqual(master.total_data_blocks, builder.TOTAL_DATA_BLOCKS)
        self.assertEqual(master.hikbtree_offset, builder.HIKBTREE_OFFSET)
        self.assertEqual(master.log_offset, builder.LOG_OFFSET)
        self.assertEqual(master.log_size, builder.LOG_SIZE)
        self.assertEqual(master.init_time_unix, builder.INIT_TIME)
        self.assertEqual(master.init_time_iso, "2023-11-14T22:13:20+00:00")

    def test_video_area_bounds(self) -> None:
        master = fs.parse_master_block(self.blob)
        assert master is not None
        self.assertTrue(master.contains_video(builder.VIDEO_AREA_OFFSET))
        self.assertTrue(master.contains_video(master.video_area_end - 1))
        self.assertFalse(master.contains_video(master.video_area_end))
        self.assertFalse(master.contains_video(0))

    def test_valid_master_block_reports_no_problems(self) -> None:
        master = fs.parse_master_block(self.blob)
        assert master is not None
        self.assertEqual(fs.validate_master_block(master), [])

    def test_impossible_data_block_size_is_rejected(self) -> None:
        blob = bytearray(self.blob)
        struct.pack_into("<Q", blob, fs.MASTER_BLOCK_OFFSET + fs.MASTER_DATA_BLOCK_SIZE_OFF, 12345)
        master = fs.parse_master_block(bytes(blob))
        assert master is not None
        self.assertTrue(any("data_block_size" in problem for problem in fs.validate_master_block(master)))
        # A master sector that fails validation must not drive a walk.
        self.assertEqual(fs.list_recordings(bytes(blob)), [])

    def test_master_block_found_at_documented_offset(self) -> None:
        self.assertEqual(fs.find_master_block(self.blob), fs.MASTER_BLOCK_OFFSET)

    def test_master_block_found_when_image_starts_at_the_partition(self) -> None:
        shifted = b"\x00" * 0x8000 + self.blob[: 0x4000]
        self.assertEqual(fs.find_master_block(shifted), 0x8000 + fs.MASTER_BLOCK_OFFSET)

    def test_non_hikvision_image_yields_nothing(self) -> None:
        self.assertIsNone(fs.parse_master_block(b"\x00" * 4096))
        self.assertEqual(fs.list_recordings(b"\x5a" * (1 << 20)), [])


class HikbtreeEntryTests(HikvisionFsTestBase):
    def _entries(self, **kwargs) -> list[fs.HikbtreeEntry]:
        master = fs.parse_master_block(self.blob)
        assert master is not None
        return fs.parse_hikbtree_entries(self.blob, master.hikbtree_offset, master=master, **kwargs)

    def test_returns_exactly_the_entries_that_describe_footage(self) -> None:
        self.assertEqual(len(self._entries()), builder.EXPECTED_RECORDING_COUNT)

    def test_unallocated_slot_is_excluded_by_default_and_visible_on_request(self) -> None:
        with_unused = self._entries(include_unallocated=True)
        self.assertEqual(len(with_unused), builder.EXPECTED_RECORDING_COUNT + 1)
        unused = [item for item in with_unused if item.allocation_state == fs.STATE_UNALLOCATED]
        self.assertEqual(len(unused), 1)
        self.assertFalse(unused[0].has_footage)

    def test_allocation_states_match_the_ground_truth_plan(self) -> None:
        by_offset = {item.data_offset: item for item in self._entries()}
        self.assertEqual(len(by_offset), builder.EXPECTED_RECORDING_COUNT)
        for planned in builder.PLAN:
            entry = by_offset[planned.data_offset]
            self.assertEqual(entry.allocation_state, planned.allocation_state)
            self.assertEqual(entry.channel, planned.channel)

    def test_both_documented_deletion_modes_are_classified_deleted(self) -> None:
        deleted = [item for item in self._entries() if item.is_deleted]
        self.assertEqual(len(deleted), builder.EXPECTED_DELETED_COUNT)
        self.assertEqual(len(deleted), 2)
        master = fs.parse_master_block(self.blob)
        assert master is not None
        for entry in deleted:
            self.assertNotEqual(entry.alloc_flag, fs.ALLOC_FLAG_ALLOCATED)
            # The defining condition: flag cleared, pointer still in the video area.
            self.assertTrue(master.contains_video(entry.data_offset))

    def test_initialised_entry_keeps_residual_timestamps(self) -> None:
        """[HAN2015] section 3.2 — index cleared, the times written before it survive."""
        residual = [
            item
            for item in self._entries()
            if item.is_deleted and item.timestamp_source == fs.SOURCE_RESIDUAL
        ]
        self.assertEqual(len(residual), 1)
        self.assertEqual(residual[0].timestamp_confidence, fs.CONFIDENCE_RESIDUAL)
        self.assertIsNotNone(residual[0].start_unix)
        self.assertTrue(residual[0].timestamp_confidence_basis)

    def test_overwritten_entry_has_no_usable_index_timestamps(self) -> None:
        """[HAN2015] section 3.3 — overwriting resets start/end to the sentinel.

        This is the common case on a disk that has been recording long enough to
        wrap, so the parser must not report a time it does not have.
        """
        overwritten = [
            item
            for item in self._entries()
            if item.is_deleted and item.timestamp_source != fs.SOURCE_RESIDUAL
        ]
        self.assertEqual(len(overwritten), builder.EXPECTED_IDR_RECOVERED_COUNT)
        entry = overwritten[0]
        self.assertIsNone(entry.start_unix)
        self.assertIsNone(entry.end_unix)
        self.assertEqual(entry.timestamp_source, fs.SOURCE_UNAVAILABLE)
        self.assertIsNone(entry.timestamp_confidence)
        self.assertIn("sentinel", entry.timestamp_confidence_basis)

    def test_deleted_entries_carry_lower_confidence_than_allocated(self) -> None:
        entries = self._entries()
        allocated = [item for item in entries if item.allocation_state == fs.STATE_ALLOCATED]
        deleted = [item for item in entries if item.is_deleted]
        self.assertTrue(allocated and deleted)
        self.assertEqual(allocated[0].timestamp_confidence, fs.CONFIDENCE_INDEXED)
        for entry in deleted:
            confidence = entry.timestamp_confidence
            # Either a residual time (lower) or none at all until the IDR table is read.
            if confidence is not None:
                self.assertLess(confidence, allocated[0].timestamp_confidence)

    def test_in_progress_recording_is_surfaced_not_discarded(self) -> None:
        recording = [item for item in self._entries() if item.allocation_state == fs.STATE_RECORDING]
        self.assertEqual(len(recording), 1)
        # The sentinel means "no end time written yet" — it must not become a bogus 2038 date.
        self.assertIsNone(recording[0].start_unix)

    @staticmethod
    def _entry_offset(plan_index: int) -> int:
        """Byte offset of a planned entry, following the multi-page chain."""
        page, slot = divmod(plan_index, builder.ENTRIES_PER_PAGE)
        return (
            builder.FIRST_PAGE_OFFSET
            + page * fs.PAGE_SIZE
            + fs.PAGE_ENTRY_BASE
            + slot * fs.ENTRY_SIZE
        )

    def test_cleared_flag_outside_the_video_area_is_unallocated_not_deleted(self) -> None:
        blob = bytearray(self.blob)
        deleted_plan = next(item for item in builder.PLAN if item.allocation_state.startswith("deleted"))
        entry_at = self._entry_offset(builder.PLAN.index(deleted_plan))
        struct.pack_into("<Q", blob, entry_at + fs.ENTRY_DATA_OFFSET_OFF, 0)

        master = fs.parse_master_block(bytes(blob))
        assert master is not None
        entries = fs.parse_hikbtree_entries(bytes(blob), master.hikbtree_offset, master=master)
        self.assertEqual(len(entries), builder.EXPECTED_RECORDING_COUNT - 1)
        # That one slot is now unallocated, not deleted; the other deletion mode stays.
        self.assertEqual(
            sum(1 for item in entries if item.is_deleted),
            builder.EXPECTED_DELETED_COUNT - 1,
        )
        self.assertFalse(
            any(item.data_offset == deleted_plan.data_offset for item in entries)
        )

    def test_cyclic_page_chain_terminates(self) -> None:
        """A page pointing at itself must not loop — it stops after that page."""
        blob = bytearray(self.blob)
        struct.pack_into(
            "<Q",
            blob,
            builder.FIRST_PAGE_OFFSET + fs.PAGE_NEXT_PAGE_OFF,
            builder.FIRST_PAGE_OFFSET,
        )
        master = fs.parse_master_block(bytes(blob))
        assert master is not None
        entries = fs.parse_hikbtree_entries(
            bytes(blob), master.hikbtree_offset, master=master, include_unallocated=True
        )
        # Only the first page is reachable once its own pointer loops back.
        self.assertEqual(len(entries), builder.ENTRIES_PER_PAGE)
        self.assertEqual({e.page_offset for e in entries}, {builder.FIRST_PAGE_OFFSET})

    def test_entry_count_is_clamped_to_what_a_page_can_hold(self) -> None:
        """A corrupt count must not read past the end of its own 4 KB page."""
        blob = bytearray(self.blob)
        struct.pack_into(
            "<I", blob, builder.FIRST_PAGE_OFFSET + fs.PAGE_ENTRY_COUNT_OFF, 0xFFFFFFFF
        )
        master = fs.parse_master_block(bytes(blob))
        assert master is not None
        entries = fs.parse_hikbtree_entries(
            bytes(blob), master.hikbtree_offset, master=master, include_unallocated=True
        )
        first_page = [e for e in entries if e.page_offset == builder.FIRST_PAGE_OFFSET]
        self.assertLessEqual(len(first_page), fs.MAX_ENTRIES_PER_PAGE)

    def test_missing_hikbtree_signature_yields_nothing(self) -> None:
        blob = bytearray(self.blob)
        at = builder.HIKBTREE_OFFSET + fs.TREE_SIG_OFF
        blob[at : at + len(fs.HIKBTREE_SIG)] = b"\x00" * len(fs.HIKBTREE_SIG)
        self.assertEqual(fs.parse_hikbtree_entries(bytes(blob), builder.HIKBTREE_OFFSET), [])


class StreamMetadataTests(HikvisionFsTestBase):
    def test_sps_decodes_resolution_and_frame_rate(self) -> None:
        sps = next(
            nal for nal in caviar_nal_units() if (nal[4] if nal[:4] == b"\x00\x00\x00\x01" else nal[3]) & 0x1F == 7
        )
        payload = sps[5:] if sps[:4] == b"\x00\x00\x00\x01" else sps[4:]
        info = fs.parse_sps(payload)
        self.assertIsNotNone(info)
        assert info is not None
        self.assertEqual(info.resolution, "320x240")
        self.assertEqual(info.width, 320)
        self.assertEqual(info.height, 240)

    def test_rbsp_strips_emulation_prevention_bytes(self) -> None:
        self.assertEqual(fs._rbsp(b"\x00\x00\x03\x01"), b"\x00\x00\x01")
        self.assertEqual(fs._rbsp(b"\x00\x00\x03\x00\x00\x03\x02"), b"\x00\x00\x00\x00\x02")
        self.assertEqual(fs._rbsp(b"\x01\x02\x03"), b"\x01\x02\x03")

    def test_garbage_sps_returns_none_rather_than_a_guess(self) -> None:
        self.assertIsNone(fs.parse_sps(b""))
        self.assertIsNone(fs.parse_sps(b"\xff" * 8))

    def test_idr_table_timestamps_are_recovered_in_order(self) -> None:
        planned = builder.PLAN[0]
        block_start = planned.data_offset
        stamps = fs.idr_timestamps(self.blob, block_start, block_start + builder.DATA_BLOCK_SIZE)
        self.assertEqual(stamps, sorted(planned.idr_timestamps()))

    def test_event_type_discriminates_continuous_from_triggered(self) -> None:
        self.assertEqual(fs.classify_event_type([100, 190], 100, 200), fs.EVENT_CONTINUOUS)
        self.assertEqual(fs.classify_event_type([100, 110], 100, 200), fs.EVENT_EVENT)
        self.assertEqual(fs.classify_event_type([100], 100, 200), fs.EVENT_UNKNOWN)
        self.assertEqual(fs.classify_event_type([100, 190], None, None), fs.EVENT_UNKNOWN)

    def test_video_payload_span_excludes_the_idr_table_and_the_unwritten_tail(self) -> None:
        block_start = builder.PLAN[0].data_offset
        block_end = block_start + builder.DATA_BLOCK_SIZE
        span = fs.video_payload_span(self.blob, block_start, block_end)
        self.assertIsNotNone(span)
        assert span is not None
        start, end = span
        self.assertEqual(start, block_start)
        table_start = fs._idr_table_start(self.blob, block_start, block_end)
        self.assertIsNotNone(table_start)
        assert table_start is not None
        self.assertLess(end, table_start)
        self.assertNotEqual(self.blob[end - 1], 0)


class OutputContractTests(HikvisionFsTestBase):
    def setUp(self) -> None:
        self.recordings = HikvisionAdapter().list_recordings(self.built.path)

    def test_returns_the_exact_recording_count(self) -> None:
        self.assertEqual(len(self.recordings), builder.EXPECTED_RECORDING_COUNT)
        self.assertEqual(len(self.recordings), self.built.expected_count)

    def test_every_record_has_exactly_the_contract_fields(self) -> None:
        for record in self.recordings:
            self.assertEqual(set(record), OUTPUT_CONTRACT)

    def test_deleted_recording_is_reported_with_its_footage(self) -> None:
        deleted = [item for item in self.recordings if item["allocation_state"] == fs.STATE_DELETED]
        self.assertEqual(len(deleted), builder.EXPECTED_DELETED_COUNT)
        record = deleted[0]
        planned = next(item for item in builder.PLAN if item.allocation_state.startswith("deleted"))
        self.assertEqual(record["channel"], planned.channel)
        self.assertEqual(record["byte_offset"], planned.data_offset)
        self.assertGreater(record["byte_length"], 0)
        self.assertIsNotNone(record["start_ts"])

    def test_metadata_is_extracted_from_the_stream_not_defaulted(self) -> None:
        for record in self.recordings:
            self.assertEqual(record["resolution"], "320x240")
            self.assertEqual(record["fps"], 6.0)

    def test_event_type_matches_the_recorded_cadence(self) -> None:
        by_offset = {item["byte_offset"]: item for item in self.recordings}
        for planned in builder.PLAN:
            if planned.allocation_state == "recording":
                continue  # no declared end time to measure coverage against
            self.assertEqual(by_offset[planned.data_offset]["event_type"], planned.event_type)

    def test_both_channels_are_represented(self) -> None:
        self.assertEqual({item["channel"] for item in self.recordings}, {1, 2})

    def test_summary_counts_by_allocation_state(self) -> None:
        entries = fs.list_recordings(self.blob)
        counts = fs.summarize(entries)
        self.assertEqual(counts[fs.STATE_DELETED], builder.EXPECTED_DELETED_COUNT)
        self.assertEqual(
            counts[fs.STATE_ALLOCATED],
            sum(1 for p in builder.PLAN if p.allocation_state == "allocated"),
        )
        self.assertEqual(counts[fs.STATE_RECORDING], 1)

    def test_overwritten_recording_recovers_its_time_from_the_idr_table(self) -> None:
        """The lowest rung of the confidence ladder, end to end.

        The index timestamps are gone, so the only surviving clock is inside the
        data block. The recording must still be reported, with its time sourced
        from the IDR table and flagged at the weakest confidence.
        """
        entries = fs.list_recordings(self.blob)
        recovered = [
            item
            for item in entries
            if item.allocation_state == fs.STATE_DELETED
            and item.timestamp_source == fs.SOURCE_IDR_SCAN
        ]
        self.assertEqual(len(recovered), builder.EXPECTED_IDR_RECOVERED_COUNT)
        entry = recovered[0]
        planned = next(
            item for item in builder.PLAN if item.recovers_time_from_idr_table
        )
        expected_start, expected_end = planned.expected_recovered_window

        self.assertEqual(entry.timestamp_confidence, fs.CONFIDENCE_IDR_SCAN)
        self.assertEqual(entry.start_ts, fs.unix_to_iso(expected_start))
        self.assertEqual(entry.end_ts, fs.unix_to_iso(expected_end))
        self.assertEqual(entry.channel, planned.channel)
        self.assertEqual(entry.byte_offset, planned.data_offset)
        # The basis must say the time may belong to either recording — that is the
        # whole point of the weaker rung.
        self.assertIn("overwriting", entry.timestamp_confidence_basis)

    def test_confidence_ladder_is_ordered(self) -> None:
        """Indexed > residual > IDR-recovered, with no other values in play."""
        entries = fs.list_recordings(self.blob)
        by_source = {
            item.timestamp_source: item.timestamp_confidence for item in entries
        }
        self.assertEqual(by_source[fs.SOURCE_INDEXED], fs.CONFIDENCE_INDEXED)
        self.assertEqual(by_source[fs.SOURCE_RESIDUAL], fs.CONFIDENCE_RESIDUAL)
        self.assertEqual(by_source[fs.SOURCE_IDR_SCAN], fs.CONFIDENCE_IDR_SCAN)
        self.assertGreater(fs.CONFIDENCE_INDEXED, fs.CONFIDENCE_RESIDUAL)
        self.assertGreater(fs.CONFIDENCE_RESIDUAL, fs.CONFIDENCE_IDR_SCAN)
        self.assertEqual(
            {item.timestamp_confidence for item in entries},
            {fs.CONFIDENCE_INDEXED, fs.CONFIDENCE_RESIDUAL, fs.CONFIDENCE_IDR_SCAN},
        )


class AdapterSegmentTests(HikvisionFsTestBase):
    def setUp(self) -> None:
        self.segments = HikvisionAdapter().scan(self.built.path)

    def test_segments_mirror_the_recording_list(self) -> None:
        self.assertEqual(len(self.segments), builder.EXPECTED_RECORDING_COUNT)

    def test_no_segment_retains_payload_bytes(self) -> None:
        # Retaining payload per segment is what makes a multi-terabyte image OOM the desktop.
        for segment in self.segments:
            self.assertEqual(segment.raw_bytes, b"")

    def test_deleted_segment_is_labelled_for_the_recovery_page(self) -> None:
        deleted = [s for s in self.segments if s.validation == "hikbtree_deleted_entry"]
        self.assertEqual(len(deleted), builder.EXPECTED_DELETED_COUNT)
        evidence = deleted[0].validation_evidence
        self.assertTrue(evidence["deleted"])
        self.assertEqual(evidence["allocation_state"], fs.STATE_DELETED)
        self.assertEqual(evidence["resolution"], "320x240")
        self.assertEqual(evidence["fps"], 6.0)
        self.assertTrue(evidence["timestamp_confidence_basis"])

    def test_byte_ranges_are_inside_the_image(self) -> None:
        size = self.built.path.stat().st_size
        for segment in self.segments:
            self.assertGreater(segment.offset_end, segment.offset_start)
            self.assertLessEqual(segment.offset_end, size)

    def test_signature_evidence_records_which_checks_passed(self) -> None:
        for segment in self.segments:
            evidence = segment.signature_evidence
            self.assertTrue(evidence["hikbtree_index"])
            self.assertTrue(evidence["sps_decoded"])
            self.assertEqual(evidence["master_block_signature"], "HIKVISION@HANGZHOU")
            self.assertEqual(evidence["firmware"], "V4.30.005")


class MultiPageIndexTests(HikvisionFsTestBase):
    """The page-walk loop, exercised rather than trusted.

    A fixture that fits every entry on one 4 KB page never follows a next-page
    pointer, so the whole chain-walking path — and any bug in it — stays invisible.
    """

    def _entries(self, **kwargs) -> list[fs.HikbtreeEntry]:
        master = fs.parse_master_block(self.blob)
        assert master is not None
        return fs.parse_hikbtree_entries(
            self.blob, master.hikbtree_offset, master=master, **kwargs
        )

    def test_entries_really_do_span_multiple_pages(self) -> None:
        pages = {item.page_offset for item in self._entries(include_unallocated=True)}
        self.assertEqual(len(pages), builder.EXPECTED_INDEX_PAGES)
        self.assertGreater(len(pages), 1, "fixture no longer exercises the page walk")

    def test_every_page_in_the_chain_is_read(self) -> None:
        entries = self._entries(include_unallocated=True)
        self.assertEqual(len(entries), builder.EXPECTED_RECORDING_COUNT + 1)
        expected = {
            builder.FIRST_PAGE_OFFSET + i * fs.PAGE_SIZE
            for i in range(builder.EXPECTED_INDEX_PAGES)
        }
        self.assertEqual({item.page_offset for item in entries}, expected)

    def test_recordings_from_later_pages_are_not_lost(self) -> None:
        """The truncation bug this fixture guards against dropped tail entries."""
        entries = self._entries()
        last_page = builder.FIRST_PAGE_OFFSET + (
            builder.EXPECTED_INDEX_PAGES - 1
        ) * fs.PAGE_SIZE
        self.assertTrue(
            any(item.page_offset == last_page for item in entries),
            "no recording came from the final index page",
        )

    def test_a_broken_next_pointer_stops_the_walk_cleanly(self) -> None:
        blob = bytearray(self.blob)
        struct.pack_into(
            "<Q",
            blob,
            builder.FIRST_PAGE_OFFSET + fs.PAGE_NEXT_PAGE_OFF,
            len(blob) * 4,  # points far outside the image
        )
        master = fs.parse_master_block(bytes(blob))
        assert master is not None
        entries = fs.parse_hikbtree_entries(
            bytes(blob), master.hikbtree_offset, master=master, include_unallocated=True
        )
        # First page still read; the walk stops rather than reading out of bounds.
        self.assertEqual(len(entries), builder.ENTRIES_PER_PAGE)


class PartialOverwriteTests(HikvisionFsTestBase):
    """Partially overwritten blocks must be reported PARTIAL, never as complete.

    Detection follows [HAN2015] section 3.3: an IDR record timestamped outside the
    entry's own window proves the block carries footage from another recording.
    """

    def test_detector_needs_evidence_before_it_claims_an_overwrite(self) -> None:
        self.assertFalse(fs.detect_partial_overwrite([], 100, 200)[0])
        self.assertFalse(fs.detect_partial_overwrite([120, 150], None, None)[0])
        self.assertFalse(fs.detect_partial_overwrite([120, 150, 180], 100, 200)[0])

    def test_detector_flags_records_outside_the_declared_window(self) -> None:
        older, reason = fs.detect_partial_overwrite([50, 120, 150], 100, 200)
        self.assertTrue(older)
        self.assertIn("predate", reason)
        newer, reason = fs.detect_partial_overwrite([120, 150, 900], 100, 200)
        self.assertTrue(newer)
        self.assertIn("postdate", reason)

    def test_exactly_the_planned_block_comes_back_partial(self) -> None:
        recordings = fs.list_recordings(self.blob)
        partial = [r for r in recordings if r.recovery_status == fs.RECOVERY_PARTIAL]
        self.assertEqual(len(partial), builder.EXPECTED_PARTIAL_COUNT)
        self.assertEqual(fs.count_partial(recordings), builder.EXPECTED_PARTIAL_COUNT)

        planned = next(p for p in builder.PLAN if p.is_partially_overwritten)
        self.assertEqual(partial[0].channel, planned.channel)
        self.assertEqual(partial[0].byte_offset, planned.data_offset)

    def test_partial_recording_is_still_recovered_not_dropped(self) -> None:
        """Partial means "some of it is gone", not "throw it away"."""
        partial = next(
            r
            for r in fs.list_recordings(self.blob)
            if r.recovery_status == fs.RECOVERY_PARTIAL
        )
        self.assertGreater(partial.byte_length, 0)
        self.assertIsNotNone(partial.start_ts)
        # Still indexed by the recorder — allocation and recovery are separate axes.
        self.assertEqual(partial.allocation_state, fs.STATE_ALLOCATED)

    def test_partial_reason_states_the_evidence(self) -> None:
        partial = next(
            r
            for r in fs.list_recordings(self.blob)
            if r.recovery_status == fs.RECOVERY_PARTIAL
        )
        self.assertIn("IDR record", partial.partial_reason)
        self.assertIn("more than one recording", partial.partial_reason)
        # It must say plainly that the missing part is not reconstructed.
        self.assertIn("not reconstructed", partial.partial_reason)

    def test_intact_recordings_are_not_flagged(self) -> None:
        recordings = fs.list_recordings(self.blob)
        intact = [r for r in recordings if r.recovery_status == fs.RECOVERY_INTACT]
        self.assertEqual(
            len(intact), builder.EXPECTED_RECORDING_COUNT - builder.EXPECTED_PARTIAL_COUNT
        )
        for record in intact:
            self.assertEqual(record.partial_reason, "")


class NoDemoTheatreTests(unittest.TestCase):
    """The engine must parse real data, never construct it."""

    def test_engine_schema_module_exposes_no_builders(self) -> None:
        exported = dir(fs)
        for forbidden in ("build_master_block", "build_hikbtree_page", "build_hikbtree_header", "wrap_mpegps"):
            self.assertNotIn(forbidden, exported, f"{forbidden} must live in test support, not the engine")

    @staticmethod
    def _offending_lines(path: str, needle: str) -> list[str]:
        source = Path(path).read_text(encoding="utf-8")
        return [line.strip() for line in source.splitlines() if needle in line and not line.lstrip().startswith(("#", "*"))]

    def test_engine_source_never_materializes_the_whole_mapping(self) -> None:
        hits = self._offending_lines("engine/app/parsers/hikvision.py", "bytes(data)")
        self.assertEqual(hits, [], f"whole-mapping copy in adapter: {hits}")

    def test_engine_source_has_no_python_level_byte_scan_loop(self) -> None:
        hits = self._offending_lines("engine/app/parsers/schemas/hikvision_fs.py", "for idx in range(len(data)")
        self.assertEqual(hits, [], f"Python byte-scan loop in parser: {hits}")


class EntryIntegrityTests(HikvisionFsTestBase):
    """Audit findings F-1 and F-2: an entry that contradicts itself must not be able to
    carry the ordinary high-confidence justification, and its raw bytes must survive."""

    @staticmethod
    def _entry_offset(plan_index: int) -> int:
        page, slot = divmod(plan_index, builder.ENTRIES_PER_PAGE)
        return (
            builder.FIRST_PAGE_OFFSET
            + page * fs.PAGE_SIZE
            + fs.PAGE_ENTRY_BASE
            + slot * fs.ENTRY_SIZE
        )

    def _first_allocated_index(self) -> int:
        return next(
            i for i, item in enumerate(builder.PLAN) if item.allocation_state == fs.STATE_ALLOCATED
        )

    def _entry_at(self, blob: bytes, plan_index: int) -> fs.HikbtreeEntry:
        master = fs.parse_master_block(blob)
        assert master is not None
        entries = fs.parse_hikbtree_entries(blob, master.hikbtree_offset, master=master)
        offset = builder.PLAN[plan_index].data_offset
        return next(e for e in entries if e.data_offset == offset)

    # -- F-1 -----------------------------------------------------------------------

    def test_inverted_window_is_flagged_and_never_called_mutually_consistent(self) -> None:
        """F-1: end_ts before start_ts must not be justified as a consistent recorder write."""
        index = self._first_allocated_index()
        plan = builder.PLAN[index]
        blob = bytearray(self.blob)
        inverted_end = plan.start_unix - 1
        struct.pack_into(
            "<I", blob, self._entry_offset(index) + fs.ENTRY_END_TS_OFF, inverted_end
        )

        entry = self._entry_at(bytes(blob), index)

        # Raw evidence preserved exactly — no swap, no clamp, no repair.
        self.assertEqual(entry.start_unix, plan.start_unix)
        self.assertEqual(entry.end_unix, inverted_end)
        self.assertLess(entry.end_unix, entry.start_unix)

        # Anomaly detected and stated.
        self.assertEqual(entry.timestamp_status, fs.TIMESTAMP_INVERTED)

        # The false justification is gone and the confidence is degraded.
        self.assertNotIn("mutually consistent", entry.timestamp_confidence_basis)
        self.assertEqual(entry.timestamp_confidence, fs.CONFIDENCE_CONTRADICTORY)
        self.assertLess(entry.timestamp_confidence, fs.CONFIDENCE_INDEXED)
        self.assertIn("does not follow", entry.timestamp_confidence_basis)

    def test_inverted_window_survives_into_the_recording_and_its_evidence(self) -> None:
        index = self._first_allocated_index()
        plan = builder.PLAN[index]
        blob = bytearray(self.blob)
        struct.pack_into(
            "<I", blob, self._entry_offset(index) + fs.ENTRY_END_TS_OFF, plan.start_unix - 1
        )

        recording = next(
            r for r in fs.list_recordings(bytes(blob)) if r.byte_offset >= plan.data_offset
        )
        self.assertEqual(recording.timestamp_status, fs.TIMESTAMP_INVERTED)
        self.assertEqual(recording.timestamp_confidence, fs.CONFIDENCE_CONTRADICTORY)
        self.assertNotIn("mutually consistent", recording.timestamp_confidence_basis)
        # Both raw times still reported; neither reordered into a plausible-looking window.
        self.assertEqual(recording.start_ts, fs.unix_to_iso(plan.start_unix))
        self.assertEqual(recording.end_ts, fs.unix_to_iso(plan.start_unix - 1))
        self.assertLess(recording.end_ts, recording.start_ts)

    def test_a_sound_window_keeps_the_ordinary_indexed_confidence(self) -> None:
        """The fix must not degrade honest entries — the acceptance baseline is unchanged."""
        index = self._first_allocated_index()
        entry = self._entry_at(self.blob, index)
        self.assertEqual(entry.timestamp_status, fs.TIMESTAMP_OK)
        self.assertTrue(entry.channel_valid)
        self.assertEqual(entry.timestamp_confidence, fs.CONFIDENCE_INDEXED)
        self.assertIn("mutually consistent", entry.timestamp_confidence_basis)

    # -- F-2 -----------------------------------------------------------------------

    def test_erased_channel_byte_is_preserved_and_marked_invalid(self) -> None:
        """F-2: 0xFF is the format's erase pattern, not camera 255."""
        index = self._first_allocated_index()
        blob = bytearray(self.blob)
        blob[self._entry_offset(index) + fs.ENTRY_CHANNEL_OFF] = 0xFF

        entry = self._entry_at(bytes(blob), index)

        # Raw byte survives and is not silently reinterpreted as 0, 1 or "unknown".
        self.assertEqual(entry.channel, 0xFF)
        self.assertFalse(entry.channel_valid)
        self.assertNotEqual(entry.timestamp_confidence, fs.CONFIDENCE_INDEXED)
        self.assertNotIn("mutually consistent", entry.timestamp_confidence_basis)
        self.assertIn("erase pattern", entry.timestamp_confidence_basis)

    def test_zero_channel_is_invalid_because_the_format_counts_from_one(self) -> None:
        index = self._first_allocated_index()
        blob = bytearray(self.blob)
        blob[self._entry_offset(index) + fs.ENTRY_CHANNEL_OFF] = 0x00

        entry = self._entry_at(bytes(blob), index)
        self.assertEqual(entry.channel, 0)
        self.assertFalse(entry.channel_valid)

    def test_no_invented_channel_ceiling(self) -> None:
        """Only the two values the format rules out are rejected; 1..254 stay valid."""
        for channel in (1, 2, 16, 32, 64, 200, 254):
            self.assertTrue(fs.channel_is_plausible(channel), channel)
        self.assertFalse(fs.channel_is_plausible(fs.CHANNEL_UNSET))
        self.assertFalse(fs.channel_is_plausible(fs.CHANNEL_ERASED))

    def test_invalid_channel_reaches_the_segment_evidence(self) -> None:
        """The UI/report must not present an erased channel as an ordinary camera."""
        index = self._first_allocated_index()
        blob = bytearray(self.blob)
        blob[self._entry_offset(index) + fs.ENTRY_CHANNEL_OFF] = 0xFF
        with tempfile.TemporaryDirectory(prefix="pramaan-f2-") as tmp:
            path = Path(tmp) / "channel.img"
            path.write_bytes(bytes(blob))
            segments = HikvisionAdapter().scan(path)
        flagged = [s for s in segments if s.validation_evidence.get("channel_valid") is False]
        self.assertEqual(len(flagged), 1)
        self.assertEqual(flagged[0].channel, 0xFF)


class IndexTraversalStatusTests(HikvisionFsTestBase):
    """Audit finding F-3: normal and abnormal ends of the page walk must differ."""

    def _walk(self, blob: bytes) -> fs.HikbtreeTraversal:
        master = fs.parse_master_block(blob)
        assert master is not None
        return fs.walk_hikbtree(blob, master.hikbtree_offset, master=master)

    def test_a_normal_final_page_reports_complete(self) -> None:
        walk = self._walk(self.blob)
        self.assertEqual(walk.status, fs.TRAVERSAL_COMPLETE)
        self.assertTrue(walk.is_complete)
        self.assertEqual(walk.detail, "")
        self.assertEqual(len(walk.entries), builder.EXPECTED_RECORDING_COUNT)
        self.assertEqual(fs.recover_recordings(self.blob).traversal_status, fs.TRAVERSAL_COMPLETE)

    def test_next_pointer_past_eof_is_out_of_bounds_and_keeps_what_was_found(self) -> None:
        blob = bytearray(self.blob)
        struct.pack_into(
            "<Q", blob, builder.FIRST_PAGE_OFFSET + fs.PAGE_NEXT_PAGE_OFF, len(self.blob) * 8
        )
        walk = self._walk(bytes(blob))
        self.assertEqual(walk.status, fs.TRAVERSAL_OUT_OF_BOUNDS)
        self.assertFalse(walk.is_complete)
        self.assertIn(walk.status, fs.TRAVERSAL_INCOMPLETE)
        # Safe partial recovery is the intended design: page-1 entries are retained.
        self.assertEqual(len(walk.entries), builder.ENTRIES_PER_PAGE)

    def test_self_looping_page_reports_loop_without_hanging(self) -> None:
        blob = bytearray(self.blob)
        struct.pack_into(
            "<Q",
            blob,
            builder.FIRST_PAGE_OFFSET + fs.PAGE_NEXT_PAGE_OFF,
            builder.FIRST_PAGE_OFFSET,
        )
        walk = self._walk(bytes(blob))
        self.assertEqual(walk.status, fs.TRAVERSAL_LOOP)
        self.assertIn(walk.status, fs.TRAVERSAL_INCOMPLETE)
        self.assertEqual(len(walk.entries), builder.ENTRIES_PER_PAGE)

    def test_malformed_page_truncated_by_the_end_of_the_image_reports_malformed(self) -> None:
        """A page whose declared entries run past EOF must say so, not stop quietly."""
        blob = bytearray(self.blob)
        # Point page 1 at a page near the very end, then declare a full page of entries there.
        stub = len(blob) - fs.PAGE_ENTRY_BASE - fs.ENTRY_SIZE
        struct.pack_into("<Q", blob, builder.FIRST_PAGE_OFFSET + fs.PAGE_NEXT_PAGE_OFF, stub)
        struct.pack_into("<I", blob, stub + fs.PAGE_ENTRY_COUNT_OFF, 8)
        struct.pack_into("<Q", blob, stub + fs.PAGE_NEXT_PAGE_OFF, 0xFFFFFFFFFFFFFFFF)
        walk = self._walk(bytes(blob))
        self.assertEqual(walk.status, fs.TRAVERSAL_MALFORMED)
        self.assertIn(walk.status, fs.TRAVERSAL_INCOMPLETE)

    def test_missing_index_is_distinct_from_a_completed_empty_walk(self) -> None:
        blob = bytearray(self.blob)
        at = builder.HIKBTREE_OFFSET + fs.TREE_SIG_OFF
        blob[at : at + len(fs.HIKBTREE_SIG)] = b"\x00" * len(fs.HIKBTREE_SIG)
        walk = self._walk(bytes(blob))
        self.assertEqual(walk.status, fs.TRAVERSAL_NO_INDEX)
        self.assertFalse(walk.is_complete)
        self.assertEqual(walk.entries, [])

    def test_severed_pointer_to_the_documented_terminator_is_indistinguishable(self) -> None:
        """Honest negative result.

        docs/reference/hikvision_fs.md §6.2 defines 0xFFFFFFFFFFFFFFFF as the last-page
        marker, so a pointer overwritten with that exact value *is* a valid last page as
        far as the format can tell. The engine reports COMPLETE, and this test exists to
        record that limitation rather than let a later reader assume it is detected.
        """
        blob = bytearray(self.blob)
        struct.pack_into(
            "<Q", blob, builder.FIRST_PAGE_OFFSET + fs.PAGE_NEXT_PAGE_OFF, 0xFFFFFFFFFFFFFFFF
        )
        walk = self._walk(bytes(blob))
        self.assertEqual(walk.status, fs.TRAVERSAL_COMPLETE)
        self.assertEqual(len(walk.entries), builder.ENTRIES_PER_PAGE)

    def test_traversal_status_reaches_the_segment_evidence(self) -> None:
        """Requirement F-3.9: the API layer must not silently discard the diagnostic."""
        blob = bytearray(self.blob)
        struct.pack_into(
            "<Q",
            blob,
            builder.FIRST_PAGE_OFFSET + fs.PAGE_NEXT_PAGE_OFF,
            builder.FIRST_PAGE_OFFSET,
        )
        with tempfile.TemporaryDirectory(prefix="pramaan-f3-") as tmp:
            path = Path(tmp) / "loop.img"
            path.write_bytes(bytes(blob))
            segments = HikvisionAdapter().scan(path)
        self.assertTrue(segments)
        for segment in segments:
            self.assertEqual(
                segment.validation_evidence["index_traversal_status"], fs.TRAVERSAL_LOOP
            )
            self.assertFalse(segment.validation_evidence["index_complete"])
            self.assertIn("loops back", segment.validation_evidence["index_traversal_detail"])

    def test_a_healthy_image_reports_a_complete_index_to_the_caller(self) -> None:
        with tempfile.TemporaryDirectory(prefix="pramaan-f3ok-") as tmp:
            path = Path(tmp) / "ok.img"
            path.write_bytes(self.blob)
            segments = HikvisionAdapter().scan(path)
        self.assertTrue(segments)
        for segment in segments:
            self.assertTrue(segment.validation_evidence["index_complete"])
            self.assertEqual(segment.validation_evidence["index_traversal_detail"], "")


if __name__ == "__main__":
    unittest.main()
