from __future__ import annotations

import os
import tempfile
import unittest
import uuid

os.environ["FORENSIC_WORKSTATION_DATA"] = tempfile.mkdtemp(prefix="forensic-job-test-")

from engine.app.core.db import get_db, init_db  # noqa: E402
from engine.app.core.repository import get_persisted_job, persist_job, reconcile_interrupted_jobs  # noqa: E402


class JobReconciliationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        init_db()

    def test_running_jobs_marked_interrupted_on_restart(self) -> None:
        job_id = uuid.uuid4().hex
        persist_job(job_id, "recovery", "running", progress=42, message="Scanning")
        count = reconcile_interrupted_jobs()
        self.assertGreaterEqual(count, 1)
        row = get_persisted_job(job_id)
        assert row is not None
        self.assertEqual(row["status"], "interrupted")
        self.assertIn("Engine restarted", row["message"] or "")

    def test_completed_jobs_untouched(self) -> None:
        job_id = uuid.uuid4().hex
        persist_job(job_id, "recovery", "completed", progress=100, result={"ok": True})
        reconcile_interrupted_jobs()
        row = get_persisted_job(job_id)
        assert row is not None
        self.assertEqual(row["status"], "completed")


if __name__ == "__main__":
    unittest.main()
