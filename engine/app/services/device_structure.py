from __future__ import annotations

from pathlib import Path

from engine.app.core.repository import get_device

OEM_MARKERS: list[tuple[bytes, str]] = [
    (b"DHFS4.1", "Dahua DHFS4.1"),
    (b"DHFS4", "Dahua DHFS4"),
    (b"HIKBTREE", "Hikvision B-tree"),
    (b"DHAV", "Dahua DHAV frame"),
    (b"HKVI", "Hikvision HKVI block"),
]


def _partition_entry(index: int, entry: bytes) -> dict | None:
    part_type = entry[4]
    if part_type == 0:
        return None
    start_lba = int.from_bytes(entry[8:12], "little")
    sector_count = int.from_bytes(entry[12:16], "little")
    return {
        "label": f"Partition {index + 1} (type 0x{part_type:02x})",
        "offset": start_lba * 512,
        "size": sector_count * 512,
        "type": "partition",
        "meta": {"partition_type": part_type, "start_lba": start_lba},
        "children": [],
    }


def probe_device_structure(device_id: str) -> dict:
    device = get_device(device_id)
    if not device:
        raise ValueError("Device not found")

    path = Path(device["image_path"])
    if not path.is_file():
        raise ValueError("Evidence file missing on disk")

    size = path.stat().st_size
    root_children: list[dict] = []

    mbr = path.read_bytes()[:512]
    if len(mbr) >= 512 and mbr[510:512] == b"\x55\xaa":
        partitions = []
        for index in range(4):
            entry = mbr[446 + index * 16 : 446 + (index + 1) * 16]
            parsed = _partition_entry(index, entry)
            if parsed:
                partitions.append(parsed)
        root_children.append(
            {
                "label": "Master Boot Record",
                "offset": 0,
                "size": 512,
                "type": "mbr",
                "meta": {"signature": "0x55AA"},
                "children": partitions,
            }
        )

    if size > 512:
        gpt_header = path.read_bytes()[512:1024]
        if gpt_header.startswith(b"EFI PART"):
            root_children.append(
                {
                    "label": "GPT header",
                    "offset": 512,
                    "size": 512,
                    "type": "gpt",
                    "meta": {"signature": "EFI PART"},
                    "children": [],
                }
            )

    sample_len = min(size, 64 * 1024 * 1024)
    sample = path.read_bytes()[:sample_len]
    seen_offsets: set[int] = set()
    for token, label in OEM_MARKERS:
        start = 0
        while True:
            idx = sample.find(token, start)
            if idx < 0:
                break
            if idx not in seen_offsets:
                seen_offsets.add(idx)
                root_children.append(
                    {
                        "label": label,
                        "offset": idx,
                        "size": 4096,
                        "type": "oem_marker",
                        "meta": {"marker": token.decode("ascii", errors="replace")},
                        "children": [],
                    }
                )
            start = idx + len(token)

    try:
        import pytsk3

        img = pytsk3.Img_Info(str(path))
        volume = pytsk3.Volume_Info(img)
        tsk_partitions: list[dict] = []
        for part in volume:
            addr = int(part.addr)
            start = int(part.start) * 512
            part_size = int(part.len) * 512
            tsk_partitions.append(
                {
                    "label": f"TSK part {addr} ({part.desc.decode('utf-8', errors='replace')})",
                    "offset": start,
                    "size": part_size,
                    "type": "tsk_partition",
                    "meta": {"addr": addr, "desc": part.desc.decode("utf-8", errors="replace")},
                    "children": [],
                }
            )
        if tsk_partitions:
            root_children.append(
                {
                    "label": "The Sleuth Kit volume map",
                    "offset": 0,
                    "size": size,
                    "type": "tsk",
                    "children": tsk_partitions,
                }
            )
    except Exception:
        pass

    return {
        "device_id": device_id,
        "size_bytes": size,
        "nodes": [
            {
                "label": path.name,
                "offset": 0,
                "size": size,
                "type": "evidence_image",
                "children": root_children,
            }
        ],
    }
