from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path

from engine.app.parsers.image_io import evidence_size, read_image_bytes

# OEM labels are routing hints only. A proprietary adapter is selected only when
# its on-disk family signature is present; brand text alone never proves a filesystem.
OEM_PROFILES: list[dict] = [
    {
        "vendor": "Dahua",
        "adapter": "dahua_dhav",
        "family": "dahua",
        "tokens": [b"DHAV", b"DHFS", b"DHFS4", b"DHFS4.1", b"Dahua", b"DAHUA"],
        "weight": 1.0,
        "capability_tier": "experimental_parser",
        "validation_scope": "synthetic_and_known_fixtures",
        "user_label": "DHAV frame carver",
    },
    {
        "vendor": "Hikvision",
        "adapter": "hikvision",
        "family": "hikvision",
        "tokens": [b"HIKVISION@HANGZHOU", b"HIKBTREE", b"HIKVISION-DVR"],
        "weight": 1.0,
        "capability_tier": "experimental_parser",
        "validation_scope": "synthetic_and_known_fixtures",
    },
    {
        "vendor": "CP Plus",
        "adapter": "dahua_dhav",
        "family": "dahua",
        "tokens": [b"CPPLUS", b"CP PLUS", b"CPPlus", b"CP-PLUS"],
        "weight": 0.95,
        "required_signatures": [b"DHAV", b"DHFS4", b"DHFS4.1"],
        "capability_tier": "experimental_parser",
        "validation_scope": "signature_match_only",
        "user_label": "DHAV frame carver",
    },
    {
        "vendor": "Honeywell",
        "adapter": "honeywell",
        "family": "honeywell",
        "tokens": [b"Honeywell", b"HWDVR", b"HONHT", b"HONEYWELL"],
        "weight": 0.85,
        "capability_tier": "experimental_parser",
        "validation_scope": "synthetic_fixture_only",
    },
    {
        "vendor": "TP-Link",
        "adapter": "generic_tier2",
        "family": "generic",
        "tokens": [b"TP-LINK", b"TPLINK", b"Tapo", b"TP_LINK"],
        "weight": 0.85,
        "capability_tier": "acquisition_generic_only",
        "validation_scope": "generic_signature_carving_only",
    },
    {
        "vendor": "Godrej",
        "adapter": "generic_tier2",
        "family": "generic",
        "tokens": [b"GODREJ", b"Godrej", b"GODREJ SECURE"],
        "weight": 0.85,
        "capability_tier": "acquisition_generic_only",
        "validation_scope": "generic_signature_carving_only",
    },
    {
        "vendor": "Uniview",
        "adapter": "hikvision",
        "family": "hikvision",
        "tokens": [b"UNIVIEW", b"UNV", b"uniview", b"Uniview"],
        "weight": 0.9,
        "required_signatures": [b"HIKBTREE", b"HIKVISION@HANGZHOU"],
        "capability_tier": "experimental_parser",
        "validation_scope": "signature_match_only",
    },
    {
        "vendor": "Matrix",
        "adapter": "generic_tier2",
        "family": "generic",
        "tokens": [b"MATRIX", b"Matrix", b"COSEC", b"MATRIX COSEC"],
        "weight": 0.85,
        "capability_tier": "acquisition_generic_only",
        "validation_scope": "generic_signature_carving_only",
    },
]

FILESYSTEM_MARKERS = [
    (b"EFI PART", "GPT partition table"),
    (b"NTFS    ", "NTFS volume"),
    (b"FAT16   ", "FAT16 volume"),
    (b"FAT32   ", "FAT32 volume"),
    (b"\x55\xaa", "MBR boot signature @510"),
    (b"DHFS4.1", "Dahua DHFS partition marker"),
    (b"DHFS4", "Dahua DHFS4 index"),
    (b"HIKBTREE", "Hikvision B-tree index"),
    (b"WFS0.4", "WFS 0.4 (common Indian OEM FAT variant)"),
]

H264_NAL_TYPES = {0x67, 0x68, 0x65, 0x41, 0x61, 0x27, 0x28}


@dataclass
class VendorHit:
    vendor: str
    adapter: str
    confidence: float
    markers: list[str]
    family: str = "unknown"
    capability_tier: str = "acquisition_generic_only"
    validation_scope: str = "unvalidated"
    signature_evidence: list[str] | None = None

    def to_dict(self) -> dict:
        return asdict(self)


def _read_prefix(path: Path, nbytes: int) -> bytes:
    return read_image_bytes(path, 0, nbytes)


def _filesystem_hits(data: bytes, mbr: bytes) -> list[VendorHit]:
    hits: list[VendorHit] = []
    if len(mbr) >= 512 and mbr[510:512] == b"\x55\xaa":
        hits.append(
            VendorHit(
                vendor="Filesystem",
                adapter="generic_tier2",
                confidence=0.62,
                markers=["MBR 0x55AA"],
                family="generic",
                capability_tier="filesystem_recovery",
                validation_scope="pytsk3_tier2",
                signature_evidence=["MBR"],
            )
        )
    for token, label in FILESYSTEM_MARKERS:
        if token == b"\x55\xaa":
            continue
        if token in data:
            hits.append(
                VendorHit(
                    vendor="Filesystem",
                    adapter="generic_tier2",
                    confidence=0.6,
                    markers=[label],
                    family="generic",
                    capability_tier="filesystem_recovery",
                    validation_scope="pytsk3_tier2",
                    signature_evidence=[token.decode("latin-1", errors="replace")],
                )
            )
    if b"\x53EF" in data[1070:1090] if len(data) > 1090 else False:
        hits.append(
            VendorHit(
                vendor="Filesystem",
                adapter="generic_tier2",
                confidence=0.6,
                markers=["ext superblock"],
                family="generic",
                capability_tier="filesystem_recovery",
                validation_scope="pytsk3_tier2",
            )
        )
    return hits


def _weak_h264_hit(data: bytes) -> VendorHit | None:
    sample_len = len(data)
    if sample_len < 4096:
        return None
    h264_hits = data.count(b"\x00\x00\x01") + data.count(b"\x00\x00\x00\x01")
    density = h264_hits / max(1, sample_len / 4096)
    typed = 0
    for marker in (b"\x00\x00\x00\x01", b"\x00\x00\x01"):
        idx = 0
        while True:
            hit = data.find(marker, idx)
            if hit < 0 or hit + len(marker) >= len(data):
                break
            nal_header = data[hit + len(marker)]
            if nal_header in H264_NAL_TYPES:
                typed += 1
            idx = hit + len(marker)
    if density > 0.5 and typed >= 3:
        return VendorHit(
            vendor="Generic H.264",
            adapter="h264_carve",
            confidence=min(0.72, 0.35 + density * 0.05),
            markers=[f"NAL×{h264_hits}", f"typed×{typed}"],
            family="generic",
            capability_tier="acquisition_generic_only",
            validation_scope="annex_b_signature_only",
            signature_evidence=["Annex B NAL start code"],
        )
    return None


def identify_image(image_path: Path, sample_bytes: int = 64 * 1024 * 1024) -> dict:
    size = evidence_size(image_path)
    sample_len = min(sample_bytes, size)
    data = _read_prefix(image_path, sample_len)
    mbr = read_image_bytes(image_path, 0, 512)
    hits: list[VendorHit] = []

    for profile in OEM_PROFILES:
        markers: list[str] = []
        score = 0.0
        for token in profile["tokens"]:
            count = data.count(token)
            if count:
                markers.append(f"{token.decode('latin-1', errors='replace')}×{count}")
                score += min(count, 80) * 0.01 * profile["weight"]
        required_hits = [
            token.decode("latin-1", errors="replace")
            for token in profile.get("required_signatures", [])
            if token in data
        ]
        if markers and (not profile.get("required_signatures") or required_hits):
            confidence = min(0.98, 0.42 + score)
            hits.append(
                VendorHit(
                    vendor=profile["vendor"],
                    adapter=profile["adapter"],
                    confidence=round(confidence, 3),
                    markers=markers,
                    family=profile["family"],
                    capability_tier=profile["capability_tier"],
                    validation_scope=profile["validation_scope"],
                    signature_evidence=required_hits,
                )
            )

    hits.extend(_filesystem_hits(data, mbr))
    weak_h264 = _weak_h264_hit(data)
    if weak_h264:
        hits.append(weak_h264)

    hits.sort(key=lambda item: (0 if item.family not in {"generic"} else 1, -item.confidence))

    filesystem: list[dict] = []
    for token, label in FILESYSTEM_MARKERS:
        if token in data or (token == b"\x55\xaa" and len(mbr) >= 512 and mbr[510:512] == token):
            filesystem.append({"marker": token.decode("latin-1", errors="replace"), "label": label})

    if hits:
        recommended = hits[0].adapter
    else:
        recommended = "needs_selection"

    return {
        "image_size_bytes": size,
        "sample_bytes": sample_len,
        "hits": [hit.to_dict() for hit in hits],
        "filesystem_hints": filesystem,
        "recommended_adapter": recommended,
        "supported_oems_in_ps": [p["vendor"] for p in OEM_PROFILES],
        "oem_capabilities": [
            {
                "vendor": profile["vendor"],
                "adapter": profile["adapter"],
                "capability_tier": profile["capability_tier"],
                "validation_scope": profile["validation_scope"],
                "requires_signature_match": bool(profile.get("required_signatures")),
                "user_label": profile.get("user_label"),
            }
            for profile in OEM_PROFILES
        ],
        "coverage_note": (
            "No parser is field-validated without independent recorder media. Dahua recovery is a DHAV frame "
            "carver (DHFS4.1 is a detection marker only). Hikvision uses HIKBTREE index + MPEG-PS carve. "
            "Honeywell has a fixture-tested experimental parser. When identification is inconclusive, select an "
            "adapter manually on Recovery."
        ),
    }


def detect_vendors(image_path: Path, sample_bytes: int = 64 * 1024 * 1024) -> list[VendorHit]:
    """Backward-compatible wrapper used by acquisition and recovery."""
    report = identify_image(image_path, sample_bytes=sample_bytes)
    return [
        VendorHit(
            vendor=item["vendor"],
            adapter=item["adapter"],
            confidence=item["confidence"],
            markers=item["markers"],
            family=item.get("family", "unknown"),
            capability_tier=item.get("capability_tier", "acquisition_generic_only"),
            validation_scope=item.get("validation_scope", "unvalidated"),
            signature_evidence=item.get("signature_evidence"),
        )
        for item in report["hits"]
    ]
