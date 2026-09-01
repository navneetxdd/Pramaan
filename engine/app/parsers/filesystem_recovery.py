from __future__ import annotations

import logging
import struct
from dataclasses import dataclass
from pathlib import Path

from engine.app.parsers.base import RecoveredSegment
from engine.app.parsers.image_io import read_image_bytes

logger = logging.getLogger("forensic.engine")

VIDEO_EXTENSIONS = {".mp4", ".264", ".h264", ".h265", ".hevc", ".dav", ".mkv"}
VIDEO_MAGICS = (
    (b"\x00\x00\x00\x01", "h264_nal"),
    (b"\x00\x00\x01", "h264_nal3"),
    (b"ftyp", "mp4"),
    (b"DHAV", "dhav"),
    (b"HKVI", "hkvi"),
)


@dataclass(frozen=True)
class FilesystemRecoveryStatus:
    available: bool
    backend: str
    detail: str


def filesystem_status() -> FilesystemRecoveryStatus:
    try:
        import pytsk3  # noqa: F401

        return FilesystemRecoveryStatus(True, "pytsk3", "The Sleuth Kit filesystem introspection available")
    except ImportError:
        return FilesystemRecoveryStatus(
            False,
            "none",
            "pytsk3 not installed — Tier 2 filesystem undelete unavailable; using raw H.264 carve",
        )


def _open_tsk_image(image_path: Path):
    import pytsk3

    if image_path.suffix.lower() in {".e01", ".ex01"}:
        from engine.app.services.e01_reader import open_e01_readonly, pyewf_available

        if pyewf_available():
            handle = open_e01_readonly(image_path)

            class PyewfImg(pytsk3.Img_Info):
                def __init__(self, ewf_handle) -> None:
                    self._h = ewf_handle
                    super().__init__(url="", type=pytsk3.TSK_IMG_TYPE_EXTERNAL)

                def close(self) -> None:
                    self._h.close()

                def read(self, offset: int, size: int) -> bytes:
                    self._h.seek(offset)
                    return self._h.read(size)

                def get_size(self) -> int:
                    return int(self._h.get_media_size())

            return PyewfImg(handle)

    return pytsk3.Img_Info(str(image_path))


def _filesystem_partition_offset(img, volume) -> int:
    import pytsk3

    skip_terms = ("unallocated", "primary table", "meta", "gpt", "protective")
    candidates: list[int] = []
    block_size = volume.info.block_size
    for part in volume:
        if part.len <= 0:
            continue
        desc = part.desc.decode("utf-8", "ignore").lower()
        if any(term in desc for term in skip_terms):
            continue
        candidates.append(int(part.start) * block_size)

    for offset in candidates:
        try:
            pytsk3.FS_Info(img, offset=offset)
            return offset
        except Exception:
            continue
    return 0


def recover_filesystem(image_path: Path, *, max_entries: int = 256) -> list[RecoveredSegment]:
    status = filesystem_status()
    if not status.available:
        return manual_fat_deleted_recovery(image_path)

    import pytsk3

    segments: list[RecoveredSegment] = []
    img = _open_tsk_image(image_path)
    try:
        try:
            volume = pytsk3.Volume_Info(img)
            partition_offset = _filesystem_partition_offset(img, volume)
        except Exception:
            partition_offset = 0

        try:
            fs = pytsk3.FS_Info(img, offset=partition_offset)
        except OSError:
            logger.info("pytsk3 could not mount %s — trying manual FAT undelete", image_path)
            return manual_fat_deleted_recovery(image_path)

        root = fs.open_dir(path="/")
        if not root:
            return manual_fat_deleted_recovery(image_path)

        count = 0
        for entry in root:
            if count >= max_entries:
                break
            name = entry.info.name.name.decode("utf-8", "ignore") if entry.info.name.name else ""
            if not name or name in {".", ".."}:
                continue
            meta = entry.info.meta
            if meta is None:
                continue

            is_deleted = bool(meta.flags & 1)
            if not is_deleted and meta.type != 1:
                continue

            try:
                file_obj = entry.as_file() if hasattr(entry, "as_file") else entry
                if file_obj is None:
                    continue
                size = min(int(meta.size or 0), 8 * 1024 * 1024)
                offset = int(meta.addr) * fs.info.block_size if meta.addr else 0
                if size <= 0:
                    if not is_deleted:
                        continue
                    data = b""
                else:
                    data = file_obj.read_random(0, min(size, 4096))
            except Exception:
                continue

            magic = _classify_magic(data)
            if not is_deleted:
                if not magic and Path(name).suffix.lower() not in VIDEO_EXTENSIONS:
                    continue

            validation = "filesystem_deleted_inode" if is_deleted else "filesystem_unallocated"
            segments.append(
                RecoveredSegment(
                    channel=None,
                    vendor="Generic",
                    offset_start=offset,
                    offset_end=offset + max(size, 1),
                    frame_count=1,
                    confidence=0.84 if is_deleted else 0.72,
                    validation=validation,
                    raw_bytes=data[:512],
                )
            )
            count += 1
    finally:
        del img

    if segments:
        return segments
    return manual_fat_deleted_recovery(image_path)


def manual_fat_deleted_recovery(image_path: Path) -> list[RecoveredSegment]:
    """Walk a FAT12/16 root directory for 0xE5-deleted entries when pytsk mount fails."""
    try:
        data = read_image_bytes(image_path, 0, 512 * 256)
    except OSError:
        return []
    if len(data) < 512 or data[510:512] != b"\x55\xAA":
        return []

    bytes_per_sector = struct.unpack_from("<H", data, 11)[0]
    reserved_sectors = struct.unpack_from("<H", data, 14)[0]
    fat_count = data[16]
    root_entries = struct.unpack_from("<H", data, 17)[0]
    sectors_per_fat = struct.unpack_from("<H", data, 22)[0]
    if bytes_per_sector == 0 or fat_count == 0:
        return []

    root_sector = reserved_sectors + fat_count * sectors_per_fat
    root_offset = root_sector * bytes_per_sector
    fat_offset = reserved_sectors * bytes_per_sector
    data_start = (root_sector + (root_entries * 32 + bytes_per_sector - 1) // bytes_per_sector) * bytes_per_sector

    segments: list[RecoveredSegment] = []
    for entry_index in range(root_entries):
        entry_off = root_offset + entry_index * 32
        if entry_off + 32 > len(data):
            break
        entry = data[entry_off : entry_off + 32]
        if entry[0] != 0xE5:
            continue
        size = struct.unpack_from("<I", entry, 28)[0]
        cluster = struct.unpack_from("<H", entry, 26)[0]
        if cluster < 2 or size <= 0:
            continue
        cluster_offset = data_start + (cluster - 2) * bytes_per_sector
        if cluster_offset + size > len(data):
            continue
        payload = data[cluster_offset : cluster_offset + min(size, 4096)]
        if not _classify_magic(payload):
            continue
        segments.append(
            RecoveredSegment(
                channel=None,
                vendor="Generic",
                offset_start=cluster_offset,
                offset_end=cluster_offset + size,
                frame_count=1,
                confidence=0.83,
                validation="filesystem_deleted_inode",
                raw_bytes=payload[:512],
            )
        )
    return segments


def _classify_magic(data: bytes) -> str | None:
    for magic, label in VIDEO_MAGICS:
        if magic in data[:512]:
            return label
    return None


def build_fat16_deleted_fixture() -> bytes:
    """Minimal FAT16 image (128 sectors) with a deleted root-directory entry."""
    bytes_per_sector = 512
    reserved_sectors = 1
    fat_count = 2
    root_entries = 512
    sectors_per_fat = 1
    root_sectors = (root_entries * 32 + bytes_per_sector - 1) // bytes_per_sector
    total_sectors = 128
    data_start_sector = reserved_sectors + fat_count * sectors_per_fat + root_sectors

    boot = bytearray(bytes_per_sector)
    boot[0:3] = b"\xEB\x3C\x90"
    boot[3:11] = b"PRMAAN  "
    boot[11:13] = struct.pack("<H", bytes_per_sector)
    boot[13] = 1
    boot[14:16] = struct.pack("<H", reserved_sectors)
    boot[16] = fat_count
    boot[17:19] = struct.pack("<H", root_entries)
    boot[19:21] = struct.pack("<H", total_sectors)
    boot[21] = 0xF8
    boot[22:24] = struct.pack("<H", sectors_per_fat)
    boot[24:26] = struct.pack("<H", 63)
    boot[26:28] = struct.pack("<H", 255)
    boot[28:32] = struct.pack("<I", 0)
    boot[510:512] = b"\x55\xAA"

    image = bytearray(total_sectors * bytes_per_sector)
    image[0:512] = boot

    fat_offset = reserved_sectors * bytes_per_sector
    for fat_idx in range(fat_count):
        base = fat_offset + fat_idx * bytes_per_sector
        image[base + 4 : base + 6] = struct.pack("<H", 0xFFFF)
        image[base + 6 : base + 8] = struct.pack("<H", 0xFFFF)
        image[base + 8 : base + 10] = struct.pack("<H", 0xFFFF)

    root_offset = (reserved_sectors + fat_count * sectors_per_fat) * bytes_per_sector
    deleted_name = bytearray(11)
    deleted_name[0] = 0xE5
    deleted_name[1:9] = b"ECOVERD"
    deleted_name[9:11] = b"264"
    dirent = bytearray(32)
    dirent[0:11] = deleted_name
    dirent[11] = 0x20
    struct.pack_into("<H", dirent, 26, 2)
    struct.pack_into("<I", dirent, 28, 13)
    image[root_offset : root_offset + 32] = dirent

    cluster_offset = data_start_sector * bytes_per_sector
    payload = b"\x00\x00\x00\x01\x65DELETED_H264\x00"
    image[cluster_offset : cluster_offset + len(payload)] = payload
    return bytes(image)
