from __future__ import annotations

import os
import tempfile
import unittest
from unittest.mock import patch

os.environ.setdefault("FORENSIC_WORKSTATION_DATA", tempfile.mkdtemp(prefix="forensic-live-"))

from engine.app.core.db import get_db, init_db  # noqa: E402
from engine.app.main import app  # noqa: E402
from engine.app.services import live_devices  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402


class LiveDevicesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        init_db()
        cls.client = TestClient(app)

    def setUp(self) -> None:
        self._env_patch = patch.dict(os.environ, {"PRAMAAN_ALLOW_LOGICAL_ACQUIRE": "1"})
        self._env_patch.start()

    def tearDown(self) -> None:
        self._env_patch.stop()

    def _create_case(self) -> str:
        response = self.client.post(
            "/api/v1/cases",
            json={"name": "Live devices", "examiner_name": "Examiner"},
        )
        self.assertEqual(response.status_code, 201)
        return response.json()["id"]

    def test_probe_failure_returns_502_with_stderr(self) -> None:
        case_id = self._create_case()
        with patch.object(live_devices, "_probe_rtsp", return_value="Connection refused"):
            with patch.object(
                live_devices,
                "_enumerate_channels",
                return_value=(
                    [
                        live_devices.ChannelInfo(
                            1,
                            "Channel 1",
                            "rtsp://127.0.0.1:8554/cam1",
                            "rtsp://127.0.0.1:8554/cam1",
                            None,
                        )
                    ],
                    {},
                ),
            ):
                response = self.client.post(
                    f"/api/v1/cases/{case_id}/live-devices",
                    json={
                        "actor": "Examiner",
                        "display_name": "Test",
                        "vendor": "generic_rtsp",
                        "host": "127.0.0.1",
                        "port": 8554,
                        "scheme": "rtsp",
                        "user": "",
                        "password": "",
                        "rtsp_url_override": "rtsp://127.0.0.1:8554/cam1",
                    },
                )
        self.assertEqual(response.status_code, 502)
        self.assertIn("Connection refused", response.json()["detail"])

    def test_snapshot_writes_hash_and_custody_row(self) -> None:
        case_id = self._create_case()
        with patch.object(live_devices, "_probe_rtsp", return_value=None):
            with patch.object(
                live_devices,
                "_enumerate_channels",
                return_value=(
                    [
                        live_devices.ChannelInfo(
                            1,
                            "Channel 1",
                            "rtsp://127.0.0.1:8554/cam1",
                            "rtsp://127.0.0.1:8554/cam1",
                            None,
                        )
                    ],
                    {"model": "Mock"},
                ),
            ):
                with patch.object(live_devices.subprocess, "run") as mock_run:
                    from pathlib import Path

                    from engine.app.core.repository import case_storage_dir

                    live_dir = case_storage_dir(case_id) / "live"
                    live_dir.mkdir(parents=True, exist_ok=True)
                    snap = live_dir / "20200101T000000Z_ch1.jpg"
                    snap.write_bytes(b"\xff\xd8\xff\xd8\xff\xd9")

                    def _fake_run(cmd, **kwargs):  # type: ignore[no-untyped-def]
                        out = Path(cmd[-1])
                        out.parent.mkdir(parents=True, exist_ok=True)
                        out.write_bytes(b"\xff\xd8\xff\xd8\xff\xd9")
                        return unittest.mock.Mock(returncode=0, stderr="")

                    mock_run.side_effect = _fake_run
                    created = self.client.post(
                        f"/api/v1/cases/{case_id}/live-devices",
                        json={
                            "actor": "Examiner",
                            "display_name": "Test",
                            "vendor": "generic_rtsp",
                            "host": "127.0.0.1",
                            "port": 8554,
                            "scheme": "rtsp",
                            "user": "",
                            "password": "",
                            "rtsp_url_override": "rtsp://127.0.0.1:8554/cam1",
                        },
                    )
                    device_id = created.json()["id"]
                    with get_db() as conn:
                        before_count = conn.execute(
                            "SELECT COUNT(*) AS c FROM custody_log WHERE target_id = ?",
                            (case_id,),
                        ).fetchone()["c"]
                    snap_resp = self.client.post(
                        f"/api/v1/live-devices/{device_id}/snapshot",
                        json={"actor": "Examiner", "channel": 1},
                    )
        self.assertEqual(snap_resp.status_code, 200, snap_resp.text)
        body = snap_resp.json()
        self.assertEqual(len(body["sha256"]), 64)
        with get_db() as conn:
            after_count = conn.execute(
                "SELECT COUNT(*) AS c FROM custody_log WHERE target_id = ?",
                (case_id,),
            ).fetchone()["c"]
            last_action = conn.execute(
                "SELECT action FROM custody_log WHERE target_id = ? ORDER BY id DESC LIMIT 1",
                (case_id,),
            ).fetchone()["action"]
        self.assertEqual(after_count, before_count + 1)
        self.assertEqual(last_action, "live_snapshot_captured")

    def test_capture_registers_live_stream_evidence(self) -> None:
        case_id = self._create_case()
        with patch.object(live_devices, "_probe_rtsp", return_value=None):
            with patch.object(
                live_devices,
                "_enumerate_channels",
                return_value=(
                    [
                        live_devices.ChannelInfo(
                            1,
                            "Channel 1",
                            "rtsp://127.0.0.1:8554/cam1",
                            "rtsp://127.0.0.1:8554/cam1",
                            None,
                        )
                    ],
                    {},
                ),
            ):
                with patch.object(live_devices.subprocess, "run") as mock_run:
                    from pathlib import Path

                    def _fake_run(cmd, **kwargs):  # type: ignore[no-untyped-def]
                        out = Path(cmd[-1])
                        out.parent.mkdir(parents=True, exist_ok=True)
                        out.write_bytes(b"\x00\x00\x00\x18ftypmp42\x00" + b"\x00" * 64)
                        return unittest.mock.Mock(returncode=0, stderr="")

                    mock_run.side_effect = _fake_run
                    created = self.client.post(
                        f"/api/v1/cases/{case_id}/live-devices",
                        json={
                            "actor": "Examiner",
                            "display_name": "Test",
                            "vendor": "generic_rtsp",
                            "host": "127.0.0.1",
                            "port": 8554,
                            "scheme": "rtsp",
                            "user": "",
                            "password": "",
                            "rtsp_url_override": "rtsp://127.0.0.1:8554/cam1",
                        },
                    )
                    device_id = created.json()["id"]
                    capture = self.client.post(
                        f"/api/v1/live-devices/{device_id}/capture",
                        json={"actor": "Examiner", "channel": 1, "duration_s": 10},
                    )
        self.assertEqual(capture.status_code, 200, capture.text)
        evidence = capture.json()["evidence"]
        with get_db() as conn:
            row = conn.execute(
                "SELECT acquisition_method FROM devices WHERE id = ?",
                (evidence["id"],),
            ).fetchone()
        self.assertEqual(row["acquisition_method"], "live_stream_capture")


if __name__ == "__main__":
    unittest.main()
