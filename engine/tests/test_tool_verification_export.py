from __future__ import annotations

import asyncio
import os
import tempfile
import unittest

os.environ.setdefault("FORENSIC_WORKSTATION_DATA", tempfile.mkdtemp(prefix="forensic-toolverifyexport-"))

from engine.app.core.db import init_db  # noqa: E402
from engine.app.core.job_manager import job_manager  # noqa: E402
from engine.app.services.tool_verification_report import build_html_report, build_json_report, build_pdf_report  # noqa: E402
from engine.app.verification.run_suite import run_verification_suite  # noqa: E402


class ToolVerificationExportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        init_db()

    def test_signed_export_reports(self) -> None:
        async def _run_suite() -> str:
            job = await job_manager.create("tool_verification")
            result = await run_verification_suite(job.id)
            return result["run_id"]

        run_id = asyncio.run(_run_suite())
        report = build_json_report(run_id)
        self.assertEqual(report["run_id"], run_id)
        self.assertGreaterEqual(report["stage_count"], 9)
        html = build_html_report(run_id)
        self.assertIn("tool verification", html.lower())
        self.assertIn(run_id, html)
        signed, fingerprint = build_pdf_report(run_id)
        self.assertTrue(signed.startswith(b"%PDF"))
        self.assertGreater(len(fingerprint), 16)


if __name__ == "__main__":
    unittest.main()
