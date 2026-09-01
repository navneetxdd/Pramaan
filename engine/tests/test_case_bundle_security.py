from __future__ import annotations

import tempfile
import unittest
import zipfile
from pathlib import Path

from engine.app.core.signing import (
    certificate_fingerprint,
    sign_manifest_bytes,
    signing_certificate_pem,
    verify_manifest_bytes,
)
from engine.app.services.case_bundle import _extract_bundle_safely


class CaseBundleSecurityTests(unittest.TestCase):
    def test_archive_traversal_is_rejected(self) -> None:
        root = Path(tempfile.mkdtemp(prefix="pramaan-bundle-security-"))
        archive = root / "traversal.pramaan.zip"
        extract_dir = root / "extract"
        extract_dir.mkdir()
        with zipfile.ZipFile(archive, "w") as zf:
            zf.writestr("../outside.txt", b"must not escape")

        with self.assertRaisesRegex(ValueError, "Unsafe archive path"):
            _extract_bundle_safely(archive, extract_dir)
        self.assertFalse((root / "outside.txt").exists())

    def test_embedded_certificate_verifies_without_local_key_lookup(self) -> None:
        payload = b'{"case_id":"portable-evidence"}'
        certificate_pem = signing_certificate_pem()
        fingerprint = certificate_fingerprint()
        signature, used_fingerprint = sign_manifest_bytes(payload)

        self.assertEqual(used_fingerprint, fingerprint)
        self.assertTrue(
            verify_manifest_bytes(
                payload,
                signature,
                certificate_pem=certificate_pem,
                expected_fingerprint=fingerprint,
            )
        )
        self.assertFalse(
            verify_manifest_bytes(
                payload + b"tampered",
                signature,
                certificate_pem=certificate_pem,
                expected_fingerprint=fingerprint,
            )
        )


if __name__ == "__main__":
    unittest.main()
