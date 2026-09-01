from __future__ import annotations

import datetime
import base64
import hashlib
import hmac
import logging
from io import BytesIO
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
from pyhanko.keys import load_certs_from_pemder_data, load_private_key_from_pemder_data
from pyhanko.pdf_utils.incremental_writer import IncrementalPdfFileWriter
from pyhanko.sign import signers
from pyhanko.sign.fields import SigFieldSpec
from pyhanko_certvalidator.registry import SimpleCertificateStore

from engine.app.core.config import WORK_DIR

logger = logging.getLogger("forensic.engine")

SIGNING_DIR = WORK_DIR / "signing"
KEY_PATH = SIGNING_DIR / "signing_key.pem"
CERT_PATH = SIGNING_DIR / "signing_cert.pem"
KEYRING_SERVICE = "Pramaan Forensic Workstation"
KEYRING_ACCOUNT = f"signing-key-{hashlib.sha256(str(WORK_DIR.resolve()).encode('utf-8')).hexdigest()[:24]}"

_signer_cache: signers.SimpleSigner | None = None
_fingerprint_cache: str | None = None


def certificate_fingerprint() -> str:
    global _fingerprint_cache
    if _fingerprint_cache is None:
        _, _fingerprint_cache = _load_or_create_signer()
    return _fingerprint_cache


def signing_certificate_pem() -> str:
    _load_or_create_signer()
    return CERT_PATH.read_text(encoding="ascii")


def signing_storage_backend() -> str:
    if _load_key_from_keyring() is not None:
        return "os_credential_store"
    return "restricted_file_fallback"


def _load_key_from_keyring() -> rsa.RSAPrivateKey | None:
    try:
        import keyring

        encoded = keyring.get_password(KEYRING_SERVICE, KEYRING_ACCOUNT)
        if not encoded:
            return None
        key = serialization.load_pem_private_key(base64.b64decode(encoded), password=None)
        return key if isinstance(key, rsa.RSAPrivateKey) else None
    except Exception:
        return None


def _store_key_in_keyring(key_bytes: bytes) -> bool:
    try:
        import keyring

        keyring.set_password(KEYRING_SERVICE, KEYRING_ACCOUNT, base64.b64encode(key_bytes).decode("ascii"))
        return True
    except Exception:
        logger.warning("OS credential storage unavailable; using a restricted key file")
        return False


def _persist_material(key: rsa.RSAPrivateKey, cert: x509.Certificate) -> None:
    SIGNING_DIR.mkdir(parents=True, exist_ok=True)
    key_bytes = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )
    if _store_key_in_keyring(key_bytes):
        KEY_PATH.unlink(missing_ok=True)
    else:
        KEY_PATH.write_bytes(key_bytes)
        try:
            KEY_PATH.chmod(0o600)
        except OSError:
            logger.warning("Could not restrict signing key permissions at %s", KEY_PATH)
    CERT_PATH.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    logger.info("Persisted signing certificate; private key backend=%s", signing_storage_backend())


def _load_persisted_material() -> tuple[rsa.RSAPrivateKey, x509.Certificate] | None:
    if not CERT_PATH.exists():
        return None
    try:
        key = _load_key_from_keyring()
        if key is None and KEY_PATH.exists():
            loaded = serialization.load_pem_private_key(KEY_PATH.read_bytes(), password=None)
            key = loaded if isinstance(loaded, rsa.RSAPrivateKey) else None
        cert = x509.load_pem_x509_certificate(CERT_PATH.read_bytes())
        if key is None:
            return None
        public_key = cert.public_key()
        if not isinstance(public_key, rsa.RSAPublicKey) or key.public_key().public_numbers() != public_key.public_numbers():
            logger.error("Persisted signing key does not match the certificate")
            return None
        return key, cert
    except Exception:
        logger.exception("Failed to load persisted signing material")
        return None


def _create_signing_material() -> tuple[rsa.RSAPrivateKey, x509.Certificate]:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Pramaan Local CA")])
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(subject)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(datetime.datetime.now(datetime.timezone.utc))
        .not_valid_after(datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=3650))
        .sign(key, hashes.SHA256())
    )
    _persist_material(key, cert)
    return key, cert


def _build_signer(key: rsa.RSAPrivateKey, cert: x509.Certificate) -> tuple[signers.SimpleSigner, str]:
    fingerprint = cert.fingerprint(hashes.SHA256()).hex()
    cert_der = cert.public_bytes(serialization.Encoding.DER)
    key_der = key.private_bytes(
        serialization.Encoding.DER,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )
    asn1_cert = next(iter(load_certs_from_pemder_data(cert_der)))
    asn1_key = load_private_key_from_pemder_data(key_der, None)
    cert_registry = SimpleCertificateStore.from_certs([asn1_cert])
    signer = signers.SimpleSigner(
        signing_cert=asn1_cert,
        signing_key=asn1_key,
        cert_registry=cert_registry,
    )
    return signer, fingerprint


def _load_or_create_signer() -> tuple[signers.SimpleSigner, str]:
    global _signer_cache, _fingerprint_cache
    if _signer_cache is not None and _fingerprint_cache is not None:
        return _signer_cache, _fingerprint_cache

    material = _load_persisted_material()
    if material is None:
        logger.info("Creating new PAdES signing certificate")
        material = _create_signing_material()
    else:
        logger.info("Loaded persisted PAdES signing certificate from %s", SIGNING_DIR)

    _signer_cache, _fingerprint_cache = _build_signer(material[0], material[1])
    return _signer_cache, _fingerprint_cache


def sign_pdf_bytes(pdf_bytes: bytes) -> tuple[bytes, str]:
    signer, fingerprint = _load_or_create_signer()
    writer = IncrementalPdfFileWriter(BytesIO(pdf_bytes))
    meta = signers.PdfSignatureMetadata(field_name="ForensicSignature")
    pdf_signer = signers.PdfSigner(meta, signer=signer, new_field_spec=SigFieldSpec(sig_field_name="ForensicSignature"))
    out = BytesIO()
    pdf_signer.sign_pdf(writer, output=out)
    return out.getvalue(), fingerprint


def sign_manifest_bytes(payload: bytes) -> tuple[str, str]:
    """Return (base64 signature, certificate fingerprint) for arbitrary manifest bytes."""
    from cryptography.hazmat.primitives.asymmetric import padding

    material = _load_persisted_material()
    if material is None:
        material = _create_signing_material()
    key, cert = material
    signature = key.sign(
        payload,
        padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH),
        hashes.SHA256(),
    )
    fingerprint = cert.fingerprint(hashes.SHA256()).hex()
    return base64.b64encode(signature).decode("ascii"), fingerprint


def verify_manifest_bytes(
    payload: bytes,
    signature_b64: str,
    certificate_pem: str | None = None,
    expected_fingerprint: str | None = None,
) -> bool:
    from cryptography.exceptions import InvalidSignature
    from cryptography.hazmat.primitives.asymmetric import padding

    try:
        if certificate_pem:
            cert = x509.load_pem_x509_certificate(certificate_pem.encode("ascii"))
        else:
            material = _load_persisted_material()
            if material is None:
                return False
            _, cert = material
        fingerprint = cert.fingerprint(hashes.SHA256()).hex()
        if expected_fingerprint and not hmac.compare_digest(fingerprint, expected_fingerprint.lower()):
            return False
        public_key = cert.public_key()
        if not isinstance(public_key, rsa.RSAPublicKey):
            return False
        public_key.verify(
            base64.b64decode(signature_b64.encode("ascii"), validate=True),
            payload,
            padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH),
            hashes.SHA256(),
        )
        return True
    except (InvalidSignature, ValueError):
        return False
