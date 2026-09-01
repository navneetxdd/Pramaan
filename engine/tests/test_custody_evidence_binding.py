from __future__ import annotations

import os
import tempfile
import unittest

os.environ.setdefault("FORENSIC_WORKSTATION_DATA", tempfile.mkdtemp(prefix="pramaan-custody-digest-"))

from fastapi.testclient import TestClient  # noqa: E402

from engine.app.core.db import get_db, init_db, verify_custody_chain  # noqa: E402
from engine.app.main import app  # noqa: E402
from engine.app.services.acquisition import create_lab_specimen  # noqa: E402
import asyncio  # noqa: E402


class CustodyEvidenceDigestTests(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls) -> None:
        init_db()
        cls.client = TestClient(app)

    async def test_acquire_binds_image_sha256_into_custody_chain(self) -> None:
        created = self.client.post(
            "/api/v1/cases",
            json={"name": "Digest bind", "examiner_name": "Examiner"},
        )
        case_id = created.json()["id"]
        result = await create_lab_specimen(case_id, "Examiner", vendor="dahua")
        sha256 = result["evidence"]["sha256"]
        with get_db() as conn:
            rows = conn.execute(
                """
                SELECT action, evidence_digest FROM custody_log
                WHERE target_type = 'case' AND target_id = ?
                ORDER BY id ASC
                """,
                (case_id,),
            ).fetchall()
        acquire_rows = [dict(r) for r in rows if r["action"] == "evidence_acquired"]
        self.assertTrue(acquire_rows)
        self.assertEqual(acquire_rows[-1]["evidence_digest"], f"sha256:{sha256}")
        status = verify_custody_chain("case", case_id)
        self.assertTrue(status["intact"])


class IntegrityReportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        init_db()
        cls.client = TestClient(app)

    def test_integrity_report_documents_broken_chain(self) -> None:
        created = self.client.post(
            "/api/v1/cases",
            json={"name": "Broken chain", "examiner_name": "Examiner"},
        )
        case_id = created.json()["id"]
        with get_db() as conn:
            conn.execute(
                "UPDATE custody_log SET actor = ? WHERE target_type = 'case' AND target_id = ?",
                ("Tampered", case_id),
            )

        for suffix in ("report", "report.html", "report.pdf"):
            blocked = self.client.get(f"/api/v1/cases/{case_id}/{suffix}")
            self.assertEqual(blocked.status_code, 409, suffix)

        integrity = self.client.get(f"/api/v1/cases/{case_id}/report/integrity")
        self.assertEqual(integrity.status_code, 200)
        body = integrity.json()
        self.assertFalse(body["custody_chain_valid"]["ok"])
        self.assertIsNotNone(body["custody_chain_valid"]["first_broken_row_id"])

        html = self.client.get(f"/api/v1/cases/{case_id}/report/integrity.html")
        self.assertEqual(html.status_code, 200)
        self.assertIn("BROKEN", html.text)

        pdf = self.client.get(f"/api/v1/cases/{case_id}/report/integrity.pdf")
        self.assertEqual(pdf.status_code, 200)
        self.assertTrue(pdf.content.startswith(b"%PDF"))


if __name__ == "__main__":
    unittest.main()
