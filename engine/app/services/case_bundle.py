from __future__ import annotations

import hashlib
import json
import logging
import shutil
import stat
import uuid
import zipfile
from pathlib import Path, PurePosixPath

from engine.app import __version__
from engine.app.core.config import BUNDLES_DIR, CASES_DIR
from engine.app.core.db import utc_now
from engine.app.core.hashing import hash_file
from engine.app.core.repository import (
    case_storage_dir,
    get_case,
    import_case_bundle_rows,
    list_ai_findings_for_device,
    list_custody_for_case,
    list_devices,
    list_sequences,
    verify_device_integrity,
)
from engine.app.core.signing import (
    certificate_fingerprint,
    sign_manifest_bytes,
    signing_certificate_pem,
    verify_manifest_bytes,
)

logger = logging.getLogger("forensic.engine")

BUNDLE_FORMAT = "pramaan-case-bundle"
BUNDLE_VERSION = 2
MAX_ARCHIVE_ENTRIES = 250_000
MAX_MANIFEST_BYTES = 32 * 1024 * 1024
DISK_RESERVE_BYTES = 100 * 1024 * 1024


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            block = handle.read(4 * 1024 * 1024)
            if not block:
                break
            digest.update(block)
    return digest.hexdigest()


def _safe_member_path(root: Path, archive_path: str) -> Path:
    posix_path = PurePosixPath(archive_path)
    if posix_path.is_absolute() or not posix_path.parts or ".." in posix_path.parts:
        raise ValueError(f"Unsafe archive path: {archive_path}")
    if len(archive_path) > 1024:
        raise ValueError("Archive path exceeds the supported length")
    destination = (root / Path(*posix_path.parts)).resolve()
    if not destination.is_relative_to(root.resolve()):
        raise ValueError(f"Archive path escapes the import directory: {archive_path}")
    return destination


def _extract_bundle_safely(bundle_path: Path, extract_dir: Path) -> None:
    with zipfile.ZipFile(bundle_path, "r") as zf:
        members = zf.infolist()
        if len(members) > MAX_ARCHIVE_ENTRIES:
            raise ValueError(f"Bundle contains too many entries ({len(members)})")
        total_size = sum(member.file_size for member in members if not member.is_dir())
        available = shutil.disk_usage(extract_dir).free - DISK_RESERVE_BYTES
        if total_size > max(0, available):
            raise ValueError("Bundle cannot be extracted safely: insufficient free disk space")

        for member in members:
            if member.flag_bits & 0x1:
                raise ValueError(f"Encrypted archive entries are unsupported: {member.filename}")
            mode = member.external_attr >> 16
            if stat.S_ISLNK(mode):
                raise ValueError(f"Symbolic links are not allowed in case bundles: {member.filename}")
            destination = _safe_member_path(extract_dir, member.filename)
            if member.is_dir():
                destination.mkdir(parents=True, exist_ok=True)
                continue
            destination.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(member, "r") as source, destination.open("wb") as output:
                shutil.copyfileobj(source, output, length=4 * 1024 * 1024)


def _collect_case_payload(case_id: str) -> dict:
    case = get_case(case_id)
    if not case:
        raise ValueError("Case not found")

    devices = list_devices(case_id)
    sequences: list[dict] = []
    ai_findings: list[dict] = []
    for device in devices:
        sequences.extend(list_sequences(device["id"]))
        ai_findings.extend(list_ai_findings_for_device(device["id"]))

    custody = list_custody_for_case(case_id)
    return {
        "case": dict(case),
        "devices": devices,
        "sequences": sequences,
        "custody": custody,
        "ai_findings": ai_findings,
    }


def export_case_bundle(case_id: str, actor: str) -> Path:
    payload = _collect_case_payload(case_id)
    bundle_id = uuid.uuid4().hex
    bundle_path = BUNDLES_DIR / f"{case_id}_{bundle_id}.pramaan.zip"
    staging = BUNDLES_DIR / f".staging_{bundle_id}"
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir(parents=True)

    file_entries: list[dict] = []

    def add_file(source: Path, archive_name: str) -> None:
        if not source.exists():
            raise FileNotFoundError(f"Missing bundle file: {source}")
        dest = staging / archive_name
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, dest)
        file_entries.append(
            {
                "archive_path": archive_name.replace("\\", "/"),
                "sha256": _sha256_file(dest),
                "size_bytes": dest.stat().st_size,
            }
        )

    for device in payload["devices"]:
        image_path = Path(device["image_path"])
        archive = f"files/devices/{device['id']}/{image_path.name}"
        add_file(image_path, archive)
        device["bundle_image_path"] = archive

    for seq in payload["sequences"]:
        output_path = Path(seq["output_path"])
        if output_path.exists():
            archive = f"files/sequences/{seq['id']}/{output_path.name}"
            add_file(output_path, archive)
            seq["bundle_output_path"] = archive

    signer_certificate = signing_certificate_pem()
    signer_fingerprint = certificate_fingerprint()
    manifest_core = {
        "format": BUNDLE_FORMAT,
        "bundle_version": BUNDLE_VERSION,
        "app_version": __version__,
        "exported_at": utc_now(),
        "exported_by": actor,
        "case": payload["case"],
        "devices": payload["devices"],
        "sequences": payload["sequences"],
        "custody": payload["custody"],
        "ai_findings": payload["ai_findings"],
        "files": file_entries,
        "signer_certificate_pem": signer_certificate,
        "signer_fingerprint": signer_fingerprint,
    }
    manifest_bytes = json.dumps(manifest_core, sort_keys=True, separators=(",", ":")).encode("utf-8")
    signature, fingerprint = sign_manifest_bytes(manifest_bytes)
    if fingerprint != signer_fingerprint:
        raise RuntimeError("Signing certificate changed during bundle export")
    manifest = {**manifest_core, "signature": signature}

    manifest_path = staging / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    with zipfile.ZipFile(bundle_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for path in staging.rglob("*"):
            if path.is_file():
                zf.write(path, path.relative_to(staging).as_posix())

    shutil.rmtree(staging)
    logger.info("Exported case %s to %s", case_id, bundle_path)
    return bundle_path


def import_case_bundle(bundle_path: Path, actor: str, *, verify_only: bool = False) -> dict:
    """Import a signed case bundle, or with verify_only=True, check it without writing anything.

    Full import refuses a case ID that already exists locally (see
    import_case_bundle_rows) — by design, so a transfer can never silently overwrite
    another case's evidence trail. That also means an examiner cannot re-import their
    own export on the machine that made it to double-check it, without first deleting
    the original. verify_only exists for exactly that: it runs the same signature check
    and the same per-file hash check against the manifest as a real import, then stops
    before touching the database or case storage — an honest "is this bundle intact"
    answer that works regardless of whether the case already exists here.
    """
    if not bundle_path.exists():
        raise ValueError("Bundle file not found")

    extract_dir = BUNDLES_DIR / f".import_{uuid.uuid4().hex}"
    extract_dir.mkdir(parents=True)

    try:
        _extract_bundle_safely(bundle_path, extract_dir)

        manifest_path = extract_dir / "manifest.json"
        if not manifest_path.exists():
            raise ValueError("manifest.json missing from bundle")
        if manifest_path.stat().st_size > MAX_MANIFEST_BYTES:
            raise ValueError("manifest.json exceeds the supported size")

        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest.get("format") != BUNDLE_FORMAT:
            raise ValueError("Unsupported bundle format")

        bundle_version = int(manifest.get("bundle_version") or 0)
        if bundle_version not in {1, BUNDLE_VERSION}:
            raise ValueError(f"Unsupported bundle version: {bundle_version}")
        signature = manifest.pop("signature", "")
        signer_fingerprint = str(manifest.get("signer_fingerprint") or "")
        signer_certificate = manifest.get("signer_certificate_pem")
        if bundle_version == 1:
            manifest.pop("signer_fingerprint", None)
            signer_certificate = None
        elif not signer_certificate or not signer_fingerprint:
            raise ValueError("Portable signer certificate or fingerprint missing from bundle")
        manifest_bytes = json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode("utf-8")
        if not verify_manifest_bytes(
            manifest_bytes,
            signature,
            certificate_pem=signer_certificate,
            expected_fingerprint=signer_fingerprint or None,
        ):
            raise ValueError("Bundle signature verification failed")

        verified_files: list[str] = []
        for entry in manifest.get("files", []):
            rel = str(entry["archive_path"])
            file_path = _safe_member_path(extract_dir, rel)
            if not file_path.exists():
                raise FileNotFoundError(f"Bundle missing archived file: {rel}")
            actual = _sha256_file(file_path)
            if actual != entry["sha256"]:
                raise ValueError(f"Hash mismatch for {rel}")
            verified_files.append(rel)

        case_row = manifest["case"]
        case_id = case_row["id"]

        if verify_only:
            return {
                "case_id": case_id,
                "files_verified": len(verified_files),
                "integrity_ok": True,
                "signer_fingerprint": signer_fingerprint,
                "already_present_locally": get_case(case_id) is not None,
                "imported": False,
            }

        storage = case_storage_dir(case_id)

        devices = manifest.get("devices", [])
        for device in devices:
            bundle_image = device.pop("bundle_image_path", None)
            if not bundle_image:
                continue
            if bundle_image not in verified_files:
                raise ValueError(f"Device payload is not declared in the signed file list: {bundle_image}")
            src = _safe_member_path(extract_dir, bundle_image)
            dest = storage / PurePosixPath(bundle_image).name
            shutil.copy2(src, dest)
            device["image_path"] = str(dest)
            md5, sha256 = hash_file(dest)
            device["image_md5"] = md5
            device["image_sha256"] = sha256

        sequences = manifest.get("sequences", [])
        seq_dir = storage / "sequences"
        seq_dir.mkdir(parents=True, exist_ok=True)
        for seq in sequences:
            bundle_output = seq.pop("bundle_output_path", None)
            if not bundle_output:
                continue
            if bundle_output not in verified_files:
                raise ValueError(f"Sequence payload is not declared in the signed file list: {bundle_output}")
            src = _safe_member_path(extract_dir, bundle_output)
            dest = seq_dir / f"{seq['id']}_{PurePosixPath(bundle_output).name}"
            shutil.copy2(src, dest)
            seq["output_path"] = str(dest)
            md5, sha256 = hash_file(dest)
            seq["output_md5"] = md5
            seq["output_sha256"] = sha256

        imported = import_case_bundle_rows(
            case_row,
            devices,
            sequences,
            manifest.get("custody", []),
            manifest.get("ai_findings", []),
            actor=actor,
        )

        integrity_ok = all(verify_device_integrity(d["id"]).get("ok") for d in devices) if devices else True
        return {
            "case": imported,
            "case_id": case_id,
            "files_verified": len(verified_files),
            "integrity_ok": integrity_ok,
            "signer_fingerprint": signer_fingerprint,
            "already_present_locally": False,
            "imported": True,
        }
    finally:
        shutil.rmtree(extract_dir, ignore_errors=True)
