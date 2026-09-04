from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("FORENSIC_WORKSTATION_DATA", tempfile.mkdtemp(prefix="forensic-transcode-"))

from engine.app.core.config import EXPORTS_DIR  # noqa: E402
from engine.app.core.db import init_db  # noqa: E402
from engine.app.main import app  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402


@unittest.skipUnless(shutil.which("ffmpeg"), "ffmpeg not installed")
class TranscodePlaybackTests(unittest.TestCase):
    """Regression coverage for the /files/{name}?transcode=1 inline-playback path.

    Carving only checks for one Annex-B start code near the carve point — real
    (non-fixture) footage can produce a byte range that starts like H.264 but isn't a
    continuous decodable stream. This used to make the endpoint hang indefinitely or
    silently return an empty "200 video/mp4". Both cases are covered here.
    """

    @classmethod
    def setUpClass(cls) -> None:
        init_db()
        cls.client = TestClient(app)
        EXPORTS_DIR.mkdir(parents=True, exist_ok=True)

    def _write_export(self, name: str, data: bytes) -> str:
        path = EXPORTS_DIR / name
        path.write_bytes(data)
        return path.name

    def test_non_decodable_carve_returns_422_not_empty_200(self) -> None:
        # One real start code (so the carver's own signature check would pass) followed by
        # a long run that never forms another valid NAL — the exact shape of the real bug.
        garbage = b"\x00\x00\x00\x01" + b"\xff" * 200_000
        filename = self._write_export("regression_non_decodable.h264", garbage)

        response = self.client.get(f"/api/v1/files/{filename}", params={"transcode": 1})

        self.assertEqual(response.status_code, 422)
        self.assertIn("no decodable video frames", response.json()["detail"])

    def test_genuinely_decodable_stream_still_plays(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source_h264 = Path(tmp) / "source.h264"
            subprocess.run(
                [
                    "ffmpeg",
                    "-y",
                    "-hide_banner",
                    "-loglevel",
                    "error",
                    "-f",
                    "lavfi",
                    "-i",
                    "color=c=black:s=64x64:d=1:r=5",
                    "-c:v",
                    "libx264",
                    "-f",
                    "h264",
                    str(source_h264),
                ],
                check=True,
            )
            filename = self._write_export("regression_decodable.h264", source_h264.read_bytes())

        response = self.client.get(f"/api/v1/files/{filename}", params={"transcode": 1})

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.content.startswith(b"\x00\x00\x00"))
        self.assertGreater(len(response.content), 0)

        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as tmp_out:
            tmp_out.write(response.content)
            out_path = tmp_out.name
        probe = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "stream=nb_frames,codec_name",
                "-of",
                "default=noprint_wrappers=1",
                out_path,
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(probe.returncode, 0, probe.stderr)
        self.assertIn("codec_name=h264", probe.stdout)


if __name__ == "__main__":
    unittest.main()
