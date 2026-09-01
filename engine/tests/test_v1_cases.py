from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

# Use isolated DB for tests
os.environ["FORENSIC_WORKSTATION_DATA"] = tempfile.mkdtemp(prefix="forensic-test-")

from engine.app.core.db import get_db, init_db, verify_custody_chain  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from engine.app.main import app  # noqa: E402


class V1CasesApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        init_db()
        cls.client = TestClient(app)

    def test_create_list_get_delete_case(self) -> None:
        created = self.client.post(
            "/api/v1/cases",
            json={"name": "Unit Test Case", "examiner_name": "Tester", "notes": "pytest"},
        )
        self.assertEqual(created.status_code, 201)
        body = created.json()
        case_id = body["id"]
        self.assertEqual(body["name"], "Unit Test Case")

        listing = self.client.get("/api/v1/cases")
        self.assertEqual(listing.status_code, 200)
        self.assertTrue(any(c["id"] == case_id for c in listing.json()))

        detail = self.client.get(f"/api/v1/cases/{case_id}")
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(detail.json()["devices"], [])

        custody = self.client.get(f"/api/v1/cases/{case_id}/custody-log/status")
        self.assertEqual(custody.status_code, 200)
        self.assertTrue(custody.json()["intact"])

        deleted = self.client.delete(f"/api/v1/cases/{case_id}")
        self.assertEqual(deleted.status_code, 204)

    def test_version_endpoint(self) -> None:
        response = self.client.get("/api/v1/version")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["status"], "ok")
        self.assertIn("capabilities", body)
        self.assertIn("version", body)
        self.assertIn("ffmpeg_available", body["capabilities"])

    def test_custody_chain_integrity(self) -> None:
        import uuid

        case_id = f"chain-{uuid.uuid4().hex[:8]}"
        with get_db() as conn:
            conn.execute(
                """
                INSERT INTO cases (id, name, examiner_name, created_at, notes)
                VALUES (?, 'Chain', 'Examiner', '2026-01-01T00:00:00Z', NULL)
                """,
                (case_id,),
            )
        status = verify_custody_chain("case", case_id)
        self.assertTrue(status["intact"])


if __name__ == "__main__":
    unittest.main()
