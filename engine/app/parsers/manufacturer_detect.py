from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path

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
    },
    {
        "vendor": "Hikvision",
        "adapter": "hikvision",
        "family": "hikvision",
        "tokens": [b"HKVI", b"HIKVISION", b"HIKV", b"hkvs", b"HIKVISION-DVR"],
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
        "required_signatures": [b"HKVI", b"HIKBTREE"],
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
    (b"DHFS4.1", "Dahua DHFS partition"),
    (b"DHFS4", "Dahua DHFS4 index"),
    (b"HIKBTREE", "Hikvision B-tree index"),
    (b"HKVI", "Hikvision video index block"),
    (b"WFS0.4", "WFS 0.4 (common Indian OEM FAT variant)"),
]


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
    with path.open("rb") as handle:
        return handle.read(nbytes)


def identify_image(image_path: Path, sample_bytes: int = 64 * 1024 * 1024) -> dict:
    data = _read_prefix(image_path, sample_bytes)
    size = image_path.stat().st_size
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

    h264_hits = data.count(b"\x00\x00\x01") + data.count(b"\x00\x00\x00\x01")
    if h264_hits > 20 and not hits:
        hits.append(
            VendorHit(
                vendor="Generic H.264",
                adapter="h264_carve",
                confidence=min(0.72, 0.35 + h264_hits * 0.002),
                markers=[f"NAL×{h264_hits}"],
                family="generic",
                capability_tier="acquisition_generic_only",
                validation_scope="annex_b_signature_only",
                signature_evidence=["Annex B NAL start code"],
            )
        )

    hits.sort(key=lambda item: item.confidence, reverse=True)

    filesystem: list[dict] = []
    for token, label in FILESYSTEM_MARKERS:
        if token in data:
            filesystem.append({"marker": token.decode("latin-1", errors="replace"), "label": label})

    recommended = hits[0].adapter if hits else "h264_carve"
    return {
        "image_size_bytes": size,
        "sample_bytes": min(sample_bytes, size),
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
            }
            for profile in OEM_PROFILES
        ],
        "coverage_note": (
            "No parser is field-validated without independent recorder media. Dahua, Hikvision, and Honeywell "
            "have fixture-tested experimental parsers; CP Plus and Uniview require matching family signatures; "
            "TP-Link, Godrej, and Matrix remain acquisition plus generic analysis only."
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
