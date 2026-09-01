from __future__ import annotations

import os
import tempfile
import unittest

os.environ.setdefault("FORENSIC_WORKSTATION_DATA", tempfile.mkdtemp(prefix="forensic-signing-test-"))

from engine.app.core.config import WORK_DIR  # noqa: E402
from engine.app.core.signing import (  # noqa: E402
    CERT_PATH,
    KEY_PATH,
    SIGNING_DIR,
    certificate_fingerprint,
    sign_pdf_bytes,
)


class SigningPersistenceTests(unittest.TestCase):
    def setUp(self) -> None:
        SIGNING_DIR.mkdir(parents=True, exist_ok=True)
        for path in (KEY_PATH, CERT_PATH):
            if path.exists():
                path.unlink()

    def test_certificate_persists_across_reload(self) -> None:
        import engine.app.core.signing as signing

        signing._signer_cache = None
        signing._fingerprint_cache = None
        first = certificate_fingerprint()
        self.assertTrue(KEY_PATH.exists())
        self.assertTrue(CERT_PATH.exists())

        signing._signer_cache = None
        signing._fingerprint_cache = None
        second = certificate_fingerprint()
        self.assertEqual(first, second)

    def test_sign_pdf_uses_persisted_certificate(self) -> None:
        import engine.app.core.signing as signing
        from reportlab.pdfgen import canvas

        signing._signer_cache = None
        signing._fingerprint_cache = None
        fp = certificate_fingerprint()

        pdf_path = WORK_DIR / "signing_test.pdf"
        c = canvas.Canvas(str(pdf_path))
        c.drawString(72, 720, "Pramaan signing persistence test")
        c.save()
        signed, used_fp = sign_pdf_bytes(pdf_path.read_bytes())
        self.assertEqual(fp, used_fp)
        self.assertGreater(len(signed), 100)


if __name__ == "__main__":
    unittest.main()
