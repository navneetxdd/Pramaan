from __future__ import annotations

import os
import platform
import tempfile
import unittest
import uuid
from pathlib import Path

os.environ["FORENSIC_WORKSTATION_DATA"] = tempfile.mkdtemp(prefix="forensic-longpath-")

from engine.app.core.db import init_db  # noqa: E402
from engine.app.core.repository import create_case, register_device_from_path  # noqa: E402
from engine.app.services.case_bundle import (  # noqa: E402
    _long_path,
    export_case_bundle,
    import_case_bundle,
)


class LongPathHelperTests(unittest.TestCase):
    """_long_path() itself: pure, no filesystem needed."""

    @unittest.skipIf(platform.system() == "Windows", "this checks the non-Windows no-op path")
    def test_noop_on_non_windows(self) -> None:
        p = Path("/short/path.txt")
        self.assertEqual(_long_path(p), p)

    @unittest.skipUnless(platform.system() == "Windows", "extended-length prefix is Windows-only")
    def test_windows_prefixes_with_extended_length_marker(self) -> None:
        p = Path("C:/some/path.txt")
        self.assertTrue(str(_long_path(p)).startswith("\\\\?\\"))

    @unittest.skipUnless(platform.system() == "Windows", "extended-length prefix is Windows-only")
    def test_windows_does_not_double_prefix(self) -> None:
        already = Path("\\\\?\\C:\\some\\path.txt")
        self.assertEqual(_long_path(already), already)


class CaseBundleLongPathIntegrationTests(unittest.TestCase):
    """Reproduces the real bug: a case created in this session hit
    `[WinError 3] The system cannot find the path specified` exporting a real,
    ordinary evidence filename, because the bundle nests it under generated
    case/device ids (files/devices/<32 hex>/<filename>) and pushed the staging
    path past Windows' 260-character limit. A filename alone doesn't need to be
    exotic to trigger this — long descriptive camera-export names are normal.
    """

    @classmethod
    def setUpClass(cls) -> None:
        init_db()

    def test_export_and_verify_only_import_survive_a_long_filename(self) -> None:
        case = create_case("Long filename regression", "Examiner")
        case_id = case["id"]

        with tempfile.TemporaryDirectory() as tmp:
            # Long enough that the bundle's own staging structure (WORK_DIR +
            # bundles/.staging_<32 hex>/files/devices/<32 hex>/<name>) pushes past
            # 260 characters, but short enough that writing it into this short temp
            # dir first (to set the test up) still succeeds on its own.
            long_name = "CCTV_Export_" + "x" * 130 + ".mp4"
            source = Path(tmp) / long_name
            source.write_bytes(b"not a real video, just needs to exist and hash")
            register_device_from_path(case_id, "Examiner", source)

            bundle_path = export_case_bundle(case_id, "Examiner")
            self.assertTrue(bundle_path.exists())

        result = import_case_bundle(bundle_path, "Examiner", verify_only=True)
        self.assertTrue(result["imported"] is False)
        self.assertEqual(result["files_verified"], 1)
        self.assertTrue(result["already_present_locally"])


if __name__ == "__main__":
    unittest.main()
