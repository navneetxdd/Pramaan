from __future__ import annotations

import os
import tempfile
import unittest

os.environ.setdefault("FORENSIC_WORKSTATION_DATA", tempfile.mkdtemp(prefix="pramaan-report-gate-"))

from fastapi.testclient import TestClient  # noqa: E402

from engine.app.core.db import get_db, init_db  # noqa: E402
from engine.app.main import app  # noqa: E402


class ReportCustodyGateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        init_db()
        cls.client = TestClient(app)

    def test_all_report_formats_reject_a_broken_custody_chain(self) -> None:
        created = self.client.post(
            "/api/v1/cases",
            json={"name": "Custody gate", "examiner_name": "Examiner"},
        )
        self.assertEqual(created.status_code, 201)
        case_id = created.json()["id"]
        with get_db() as conn:
            conn.execute(
                "UPDATE custody_log SET actor = ? WHERE target_type = 'case' AND target_id = ?",
                ("Tampered", case_id),
            )

        for suffix in ("report", "report.html", "report.pdf"):
            response = self.client.get(f"/api/v1/cases/{case_id}/{suffix}")
            self.assertEqual(response.status_code, 409, suffix)


if __name__ == "__main__":
    unittest.main()
