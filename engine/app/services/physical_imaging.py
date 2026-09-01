from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
from pathlib import Path

from engine.app.core.config import CHECKPOINT_INTERVAL, CHUNK_SIZE
from engine.app.core.db import append_custody, get_db, utc_now
from engine.app.core.job_manager import job_manager
from engine.app.core.repository import (
    case_storage_dir,
    get_case,
    get_device,
    register_pending_device,
    save_acquisition_checkpoint,
    get_latest_acquisition_checkpoint,
    persist_job,
    update_device_acquisition,
)
from engine.app.parsers.manufacturer_detect import identify_image
from engine.app.services.disk_enumeration import (
    open_source_readonly,
    source_size_bytes,
)
from engine.app.services.e01_reader import e01_size, open_e01_readonly, pyewf_available, read_e01

logger = logging.getLogger("forensic.engine")

SECTOR_SIZE = 512


class ImagingCancelled(Exception):
    pass


def _is_e01(path: str) -> bool:
    return path.lower().endswith((".e01", ".ex01"))


def _read_at(source: object | None, e01_handle: object | None, offset: int, size: int) -> bytes:
    if e01_handle is not None:
        return read_e01(e01_handle, offset, size)
    if source is None:
        raise OSError("Acquisition source is unavailable")
    source.seek(offset)  # type: ignore[attr-defined]
    return source.read(size)  # type: ignore[attr-defined]


def _read_with_sector_recovery(
    source: object | None,
    e01_handle: object | None,
    offset: int,
    size: int,
) -> tuple[bytes, list[int]]:
    try:
        return _read_at(source, e01_handle, offset, size), []
    except OSError as first_error:
        logger.warning("Chunk read failed at byte %s; retrying sector-by-sector: %s", offset, first_error)

    recovered = bytearray()
    bad_offsets: list[int] = []
    for relative in range(0, size, SECTOR_SIZE):
        sector_size = min(SECTOR_SIZE, size - relative)
        sector_offset = offset + relative
        try:
            sector = _read_at(source, e01_handle, sector_offset, sector_size)
            if len(sector) != sector_size:
                raise OSError(f"short read: expected {sector_size}, received {len(sector)}")
            recovered.extend(sector)
        except OSError as sector_error:
            logger.warning("Unreadable sector at byte %s: %s", sector_offset, sector_error)
            bad_offsets.append(sector_offset)
            recovered.extend(b"\x00" * sector_size)
    return bytes(recovered), bad_offsets


def _hash_source_prefix(source: object | None, e01_handle: object | None, length: int) -> tuple[str, str]:
    md5 = hashlib.md5()
    sha256 = hashlib.sha256()
    offset = 0
    while offset < length:
        size = min(CHUNK_SIZE, length - offset)
        block = _read_at(source, e01_handle, offset, size)
        if len(block) != size:
            raise RuntimeError(f"Resume validation short read at byte {offset}")
        md5.update(block)
        sha256.update(block)
        offset += size
    return md5.hexdigest(), sha256.hexdigest()


async def run_imaging_job(
    job_id: str,
    case_id: str,
    device_id: str,
    actor: str,
    *,
    source_path: str,
    resume: bool = False,
    max_bytes: int | None = None,
) -> None:
    await job_manager.update(job_id, status="running", progress=0, message="Opening source (read-only)")
    persist_job(
        job_id,
        "acquisition",
        "running",
        case_id=case_id,
        device_id=device_id,
        progress=0,
        message="Opening source (read-only)",
    )
    update_device_acquisition(device_id, status="in_progress", bad_sector_map=None)

    device = get_device(device_id)
    if not device:
        await job_manager.update(job_id, status="failed", error="Device not found")
        persist_job(job_id, "acquisition", "failed", case_id=case_id, device_id=device_id, error="Device not found")
        return

    dest = Path(device["image_path"])
    dest.parent.mkdir(parents=True, exist_ok=True)

    bytes_written = 0
    bad_sectors: list[int] = []
    md5 = hashlib.md5()
    sha256 = hashlib.sha256()
    checkpoint = None

    if resume:
        checkpoint = get_latest_acquisition_checkpoint(device_id)
        if checkpoint:
            bytes_written = int(checkpoint["bytes_written"])
            await job_manager.update(job_id, message=f"Resuming at byte {bytes_written:,}")
        if dest.exists() and dest.stat().st_size > 0:
            md5, sha256 = _hash_objects_from_file(dest)

    total_size = source_size_bytes(source_path)
    e01_handle = None
    source = None
    try:
        if _is_e01(source_path):
            if not pyewf_available():
                raise RuntimeError("E01 imaging requires pyewf — use raw/DD or install pyewf")
            e01_handle = open_e01_readonly(Path(source_path))
            total_size = e01_size(e01_handle)
        else:
            source = open_source_readonly(source_path)
        if resume:
            if checkpoint is None or not dest.exists():
                raise RuntimeError("Resume requires an existing image and a durable checkpoint")
            checkpoint_bytes = int(checkpoint["bytes_written"])
            if dest.stat().st_size != checkpoint_bytes:
                raise RuntimeError(
                    f"Resume validation failed: checkpoint={checkpoint_bytes} image_size={dest.stat().st_size}"
                )
            if total_size is not None and checkpoint_bytes > total_size:
                raise RuntimeError("Resume image is larger than its source")
            source_md5, source_sha256 = _hash_source_prefix(source, e01_handle, checkpoint_bytes)
            if source_md5 != md5.hexdigest() or source_sha256 != sha256.hexdigest():
                raise RuntimeError("Resume validation failed: source prefix does not match the partial image")
            bytes_written = checkpoint_bytes
    except Exception as exc:
        await job_manager.update(job_id, status="failed", error=str(exc))
        update_device_acquisition(
            device_id,
            status="failed",
            bad_sector_map={"error": str(exc)},
            acquisition_error=str(exc),
        )
        persist_job(job_id, "acquisition", "failed", case_id=case_id, device_id=device_id, error=str(exc))
        return

    mode = "ab" if resume and dest.exists() and bytes_written > 0 else "wb"
    try:
        with dest.open(mode) as out:
            if resume and dest.stat().st_size > bytes_written:
                out.truncate(bytes_written)

            while True:
                live_job = await job_manager.get(job_id)
                if live_job and live_job.status == "cancelled":
                    raise ImagingCancelled("Acquisition cancelled by operator")
                if max_bytes is not None and bytes_written >= max_bytes:
                    break
                if total_size is not None and bytes_written >= total_size:
                    break

                read_size = CHUNK_SIZE
                if total_size is not None:
                    read_size = min(read_size, total_size - bytes_written)
                if max_bytes is not None:
                    read_size = min(read_size, max_bytes - bytes_written)
                if read_size <= 0:
                    break

                chunk, failed_offsets = _read_with_sector_recovery(
                    source,
                    e01_handle,
                    bytes_written,
                    read_size,
                )
                bad_sectors.extend(failed_offsets)

                if not chunk:
                    break

                out.write(chunk)
                md5.update(chunk)
                sha256.update(chunk)
                bytes_written += len(chunk)

                if total_size:
                    progress = min(99.0, (bytes_written / total_size) * 100)
                elif max_bytes:
                    progress = min(99.0, (bytes_written / max_bytes) * 100)
                else:
                    progress = min(99.0, bytes_written / (1024 * 1024))

                if bytes_written % CHECKPOINT_INTERVAL < len(chunk):
                    save_acquisition_checkpoint(device_id, bytes_written)
                    update_device_acquisition(
                        device_id,
                        status="in_progress",
                        bad_sector_map={"sectors": bad_sectors, "bytes_written": bytes_written},
                    )
                    persist_job(
                        job_id,
                        "acquisition",
                        "running",
                        case_id=case_id,
                        device_id=device_id,
                        progress=progress,
                        message=f"Imaged {bytes_written:,} bytes · bad sectors {len(bad_sectors)}",
                    )

                await job_manager.update(
                    job_id,
                    progress=progress,
                    message=f"Imaged {bytes_written:,} bytes · bad sectors {len(bad_sectors)}",
                )
                await asyncio.sleep(0)

            expected_bytes = (
                min(total_size, max_bytes)
                if total_size is not None and max_bytes is not None
                else total_size or max_bytes
            )
            if expected_bytes is not None and bytes_written != expected_bytes:
                raise RuntimeError(f"Acquisition ended early: expected {expected_bytes} bytes, wrote {bytes_written}")

    except ImagingCancelled as exc:
        save_acquisition_checkpoint(device_id, bytes_written)
        update_device_acquisition(
            device_id,
            status="interrupted",
            bad_sector_map={"sectors": bad_sectors, "bytes_written": bytes_written},
            acquisition_error=str(exc),
        )
        persist_job(
            job_id,
            "acquisition",
            "cancelled",
            case_id=case_id,
            device_id=device_id,
            progress=0,
            message=str(exc),
            error=str(exc),
        )
        return
    except Exception as exc:
        logger.exception("Imaging job %s failed", job_id)
        save_acquisition_checkpoint(device_id, bytes_written)
        update_device_acquisition(
            device_id,
            status="interrupted",
            bad_sector_map={"sectors": bad_sectors, "bytes_written": bytes_written},
            acquisition_error=str(exc),
        )
        await job_manager.update(job_id, status="interrupted", error=str(exc))
        persist_job(
            job_id,
            "acquisition",
            "interrupted",
            case_id=case_id,
            device_id=device_id,
            progress=0,
            error=str(exc),
        )
        return
    finally:
        if e01_handle is not None:
            e01_handle.close()
        elif source is not None:
            source.close()

    md5_hex, sha256_hex = md5.hexdigest(), sha256.hexdigest()
    copied_md5, copied_sha256 = _hash_objects_from_file(dest)
    copy_verified = copied_md5.hexdigest() == md5_hex and copied_sha256.hexdigest() == sha256_hex
    verification_status = (
        "mismatch"
        if not copy_verified
        else "verified_with_read_errors"
        if bad_sectors
        else "verified"
    )
    sidecar = dest.with_suffix(dest.suffix + ".sha256")
    sidecar.write_text(f"{sha256_hex}  {dest.name}\n", encoding="utf-8")

    identification = identify_image(dest)
    update_device_acquisition(
        device_id,
        status="complete" if copy_verified else "failed",
        md5=md5_hex,
        sha256=sha256_hex,
        bad_sector_map={"sectors": bad_sectors, "count": len(bad_sectors)},
        identification=identification,
        verification_status=verification_status,
        completed=True,
        acquisition_error=None if copy_verified else "Destination hash verification failed",
    )

    with get_db() as conn:
        append_custody(
            conn,
            actor=actor,
            action="evidence_acquired" if copy_verified else "evidence_acquisition_verification_failed",
            target_type="case",
            target_id=case_id,
            evidence_digest=f"sha256:{sha256_hex}" if sha256_hex else None,
        )

    result = {
        "case_id": case_id,
        "device_id": device_id,
        "bytes_written": bytes_written,
        "md5": md5_hex,
        "sha256": sha256_hex,
        "bad_sectors": len(bad_sectors),
        "resumed": resume,
        "verification_status": verification_status,
    }
    if not copy_verified:
        error = "Destination hash verification failed"
        await job_manager.update(job_id, status="failed", progress=100, error=error, result=result)
        persist_job(
            job_id,
            "acquisition",
            "failed",
            case_id=case_id,
            device_id=device_id,
            progress=100,
            error=error,
            result=result,
        )
        return

    await job_manager.update(job_id, status="completed", progress=100, message="Imaging complete", result=result)
    persist_job(
        job_id,
        "acquisition",
        "completed",
        case_id=case_id,
        device_id=device_id,
        progress=100,
        message="Imaging complete",
        result=result,
    )


def _hash_objects_from_file(path: Path) -> tuple[hashlib._Hash, hashlib._Hash]:
    md5 = hashlib.md5()
    sha256 = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            block = handle.read(CHUNK_SIZE)
            if not block:
                break
            md5.update(block)
            sha256.update(block)
    return md5, sha256


def _hash_from_file(path: Path) -> tuple[hashlib._Hash, hashlib._Hash]:
    return _hash_objects_from_file(path)


def prepare_imaging_device(
    case_id: str,
    actor: str,
    source_path: str,
    *,
    resume_device_id: str | None = None,
    source_type: str = "file",
    write_blocker: str = "software_read_only",
) -> dict:
    if not get_case(case_id):
        raise ValueError("Case not found")

    if resume_device_id:
        device = get_device(resume_device_id)
        if not device or device["case_id"] != case_id:
            raise ValueError("Resume device not found for case")
        return device

    source_name = Path(source_path.replace("\\\\.\\", "").replace("/", "_")).name or "evidence"
    filename = f"physical_{source_name}.dd".replace(":", "")
    dest = case_storage_dir(case_id) / filename
    device = register_pending_device(
        case_id,
        dest,
        acquisition_status="pending",
        metadata={
            "source_path": source_path,
            "source_type": source_type,
            "source_identifier": source_path,
            "source_size_bytes": source_size_bytes(source_path),
            "acquisition_method": "forensic_block_imaging",
            "acquisition_operator": actor,
            "write_blocker": write_blocker,
        },
    )
    update_device_acquisition(device["id"], status="pending", bad_sector_map={"source_path": source_path})
    return device
