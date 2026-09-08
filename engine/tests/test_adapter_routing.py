from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from engine.app.parsers.manufacturer_detect import VENDOR_PARSER_TIERS, identify_image
from engine.app.verification.honeywell_specimen import write_honeywell_specimen
from engine.app.verification.builder_specimen import write_builder_specimen


class AdapterRoutingTests(unittest.TestCase):
    def test_dahua_specimen_routes_to_dahua_adapter(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "dahua.bin"
            write_builder_specimen(path)
            report = identify_image(path)
            hits = report.get("hits") or []
            self.assertTrue(any(h.get("vendor") in {"Dahua", "CP Plus"} for h in hits))
            top = hits[0]
            self.assertIn(top.get("adapter"), {"dahua_dhav", "h264_carve"})

    def test_honeywell_specimen_routes_to_honeywell_adapter(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "honeywell.bin"
            write_honeywell_specimen(path)
            report = identify_image(path)
            hits = report.get("hits") or []
            self.assertTrue(any(h.get("vendor") == "Honeywell" for h in hits))
            top = hits[0]
            self.assertEqual(top.get("adapter"), "honeywell")

    def test_hikvision_specimen_routes_to_hikvision_adapter(self) -> None:
        from engine.app.verification.hikvision_specimen import write_hikvision_specimen

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "hikvision.bin"
            write_hikvision_specimen(path)
            report = identify_image(path)
            hits = report.get("hits") or []
            self.assertTrue(any(h.get("vendor") == "Hikvision" for h in hits))
            top = hits[0]
            self.assertEqual(top.get("adapter"), "hikvision")

    def test_rebadge_requires_family_signature(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cp_only = Path(tmp) / "cp-only.bin"
            cp_only.write_bytes(b"CPPLUS" + b"\x00" * 4096)
            cp_hits = identify_image(cp_only).get("hits") or []
            self.assertFalse(any(hit["vendor"] == "CP Plus" for hit in cp_hits))

            uniview_only = Path(tmp) / "uniview-only.bin"
            uniview_only.write_bytes(b"UNIVIEW" + b"\x00" * 4096)
            uniview_hits = identify_image(uniview_only).get("hits") or []
            self.assertFalse(any(hit["vendor"] == "Uniview" for hit in uniview_hits))

    def test_filesystem_only_image_is_not_vendor_identification(self) -> None:
        # A disk image (E01, dd) whose only signatures are an MBR and a FAT
        # volume label is filesystem-undelete territory, not a vendor match.
        # The Overview "Vendor identified" metric counts a hit only when its
        # capability_tier is in VENDOR_PARSER_TIERS, so this image must produce
        # carve hits but none at a vendor-parser tier, and route to generic.
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "disk.img"
            blob = bytearray(b"\x00" * 8192)
            blob[510:512] = b"\x55\xaa"
            blob[1024:1032] = b"FAT32   "
            path.write_bytes(bytes(blob))
            report = identify_image(path)
        hits = report.get("hits") or []
        self.assertTrue(hits, "filesystem markers should still produce carve hits")
        leaked = [h.get("capability_tier") for h in hits if h.get("capability_tier") in VENDOR_PARSER_TIERS]
        self.assertEqual(leaked, [], f"filesystem-only image leaked vendor-parser tiers: {leaked}")
        self.assertEqual(report.get("recommended_adapter"), "generic_tier2")

    def test_signature_only_hit_is_marked_as_such(self) -> None:
        # The Dahua builder specimen also carries a CP Plus token plus the DHAV
        # family signature CP Plus requires. That hit must come back at
        # capability_tier experimental_parser but validation_scope
        # signature_match_only, so the Overview "Vendor identified" metric can
        # exclude it: a family byte match is a routing hint, not an
        # identification.
        from engine.app.verification.builder_specimen import write_builder_specimen

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "dahua.bin"
            write_builder_specimen(path)
            report = identify_image(path)
        hits = report.get("hits") or []
        cpplus = next((h for h in hits if h.get("vendor") == "CP Plus"), None)
        self.assertIsNotNone(cpplus, "CP Plus token + DHAV signature should produce a hit")
        assert cpplus is not None
        self.assertEqual(cpplus["capability_tier"], "experimental_parser")
        self.assertEqual(cpplus["validation_scope"], "signature_match_only")

    def test_capability_registry_is_explicit_about_evidence_scope(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "tplink.bin"
            path.write_bytes(b"TP-LINK" + b"\x00" * 4096)
            report = identify_image(path)
        capabilities = {item["vendor"]: item for item in report["oem_capabilities"]}
        self.assertEqual(capabilities["Honeywell"]["capability_tier"], "experimental_parser")
        self.assertEqual(capabilities["TP-Link"]["capability_tier"], "acquisition_generic_only")
        self.assertTrue(capabilities["CP Plus"]["requires_signature_match"])
        self.assertTrue(capabilities["Uniview"]["requires_signature_match"])


if __name__ == "__main__":
    unittest.main()
