from __future__ import annotations

import asyncio
import unittest

from engine.app.core.job_manager import job_manager
from engine.app.verification.run_suite import run_verification_suite


class ToolVerificationTests(unittest.IsolatedAsyncioTestCase):
    async def test_verification_suite_passes(self) -> None:
        job = await job_manager.create("tool_verification")
        result = await run_verification_suite(job.id)
        self.assertTrue(result["passed"], result)
        self.assertGreaterEqual(len(result["stages"]), 9)
        stage_names = {s["stage"] for s in result["stages"]}
        self.assertIn("dahua_recovery_pipeline", stage_names)
        self.assertIn("honeywell_recovery_pipeline", stage_names)
        self.assertIn("hikvision_recovery_pipeline", stage_names)
        self.assertEqual(result.get("vendors_verified"), ["dahua", "honeywell", "hikvision"])


if __name__ == "__main__":
    unittest.main()
