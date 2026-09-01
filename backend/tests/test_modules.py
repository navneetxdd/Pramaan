import struct

from pramaan.modules.analysis.unwrap import unwrap_to_h264
from pramaan.modules.custody.hash_chain import chain_seed, compute_event_hash, verify_chain
from pramaan.recovery.adapters.dahua_dhav import DHAV_FOOTER, DHAV_HEADER


def _frame(size: int = 256) -> bytes:
    header = DHAV_HEADER + struct.pack("<I", size) + bytes([0, 0, 1, 0])
    body_len = size - len(header) - len(DHAV_FOOTER)
    payload = b"\x00\x00\x00\x01" + b"\x00" * max(0, body_len - 4)
    return header + payload[:body_len] + DHAV_FOOTER


def test_unwrap_dhav_extracts_nal():
    frame = _frame(256)
    out = unwrap_to_h264(frame)
    assert b"\x00\x00\x01" in out or b"\x00\x00\x00\x01" in out


def test_hash_chain_valid():
    case_id = "abc123"
    prev = chain_seed(case_id)
    events = []
    for i, action in enumerate(["case_created", "evidence_acquired"]):
        created = f"2026-01-01T00:00:{i:02d}+00:00"
        event_hash = compute_event_hash(prev, action, "examiner", "detail", created)
        events.append(
            {
                "id": i + 1,
                "action": action,
                "actor": "examiner",
                "detail": "detail",
                "created_at": created,
                "event_hash": event_hash,
            }
        )
        prev = event_hash
    result = verify_chain(events, case_id)
    assert result["ok"]
