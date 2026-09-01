from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from engine.app.parsers.manufacturer_detect import identify_image
from engine.app.verification.honeywell_specimen import write_honeywell_specimen
from engine.app.verification.lab_specimen import write_lab_specimen


class AdapterRoutingTests(unittest.TestCase):
    def test_dahua_specimen_routes_to_dahua_adapter(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "dahua.bin"
            write_lab_specimen(path)
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
